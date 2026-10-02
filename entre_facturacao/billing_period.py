"""Billing period ("período de facturação") for recurring Sales Invoices.

An Auto Repeat can be marked as prepaid (Antecipado: bills the period the
schedule date falls in) or postpaid (Vencido: bills the period before it).
When Auto Repeat creates a new invoice, `on_recurring` works out which period
it bills and rewrites the title and item descriptions accordingly:

- If the Auto Repeat has a template for the title / an item row, the template
  is rendered with Jinja (e.g. "Avença de {{ periodo }}").
- Otherwise, mentions of the template invoice's period ("Setembro",
  "Setembro 2026") are swapped for the new period's month/year.

Templates live on the Auto Repeat, never on the template invoice, so the
customer never sees placeholders.
"""

import re
from datetime import date

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, date_diff, formatdate, get_first_day, get_last_day, getdate, today
from jinja2 import meta

MESES = [
	"Janeiro",
	"Fevereiro",
	"Março",
	"Abril",
	"Maio",
	"Junho",
	"Julho",
	"Agosto",
	"Setembro",
	"Outubro",
	"Novembro",
	"Dezembro",
]
_MONTH_NUMBER = {m.lower(): i + 1 for i, m in enumerate(MESES)}

FREQ_MONTHS = {"Monthly": 1, "Quarterly": 3, "Half-yearly": 6, "Yearly": 12}
POSTPAID = "Vencido"

TEMPLATE_VARS = {
	"periodo",
	"mes",
	"mes_fim",
	"meses",
	"ano",
	"ano_fim",
	"data_inicio",
	"data_fim",
	"item_name",
	"item_code",
}

_SPACE = r"(?:\s|&nbsp;)+"
# "Setembro", "Setembro 2026", "Setembro de 2026" (separator and year go together)
_MONTH_RE = re.compile(
	r"\b(" + "|".join(MESES) + r")\b(?:(" + _SPACE + r"(?:de" + _SPACE + r")?)(\d{4})\b)?",
	re.IGNORECASE,
)
_TAG_RE = re.compile(r"(<[^>]*>)")


# ---------------------------------------------------------------------------
# Periods
# ---------------------------------------------------------------------------


def get_period(start, months):
	"""Period of `months` months starting on the month of `start`. Yearly
	periods are aligned to the calendar year."""
	start = getdate(start)
	start = date(start.year, 1, 1) if months == 12 else get_first_day(start)
	return frappe._dict(start=start, end=get_last_day(add_months(start, months - 1)), months=months)


def period_for_schedule(schedule_date, frequency, billing_mode):
	"""The period an invoice issued on `schedule_date` bills."""
	months = FREQ_MONTHS.get(frequency)
	if not months or not schedule_date:
		return None
	ref = getdate(schedule_date)
	if billing_mode == POSTPAID:
		ref = add_months(ref, -months)
	return get_period(ref, months)


def reference_period(period_start, posting_date, frequency, billing_mode):
	"""The period the Auto Repeat's template invoice bills: its stored
	billing_period_start if set, otherwise derived from its posting date."""
	months = FREQ_MONTHS.get(frequency)
	if not months:
		return None
	if period_start:
		return get_period(period_start, months)
	return period_for_schedule(posting_date, frequency, billing_mode)


def period_label(p):
	if p.months == 12:
		return str(p.start.year)
	first, last = MESES[p.start.month - 1], MESES[p.end.month - 1]
	if p.months == 1:
		return f"{first} {p.start.year}"
	if p.start.year == p.end.year:
		return f"{first} – {last} {p.start.year}"
	return f"{first} {p.start.year} – {last} {p.end.year}"


def period_context(p):
	return {
		"periodo": period_label(p),
		"mes": MESES[p.start.month - 1],
		"mes_fim": MESES[p.end.month - 1],
		"meses": [MESES[d.month - 1] for d in _period_months(p)],
		"ano": p.start.year,
		"ano_fim": p.end.year,
		"data_inicio": formatdate(p.start),
		"data_fim": formatdate(p.end),
	}


def periods_overlap(a, b):
	return a.start <= b.end and b.start <= a.end


def _period_months(p):
	return [add_months(p.start, i) for i in range(p.months)]


# ---------------------------------------------------------------------------
# Text rewriting
# ---------------------------------------------------------------------------


def _rewrite(text, old, month_fn, year_fn):
	"""Call month_fn / year_fn for every mention of a month (and its adjacent
	year) that belongs to the `old` period. Mentions of other months are left
	alone. Only text between HTML tags is touched."""
	if not text or not old:
		return text

	slots = [(d.year, d.month) for d in _period_months(old)]

	def repl(m):
		month = _MONTH_NUMBER[m.group(1).lower()]
		year = cint(m.group(3)) or None
		pos = next(
			(i for i, (y, mo) in enumerate(slots) if mo == month and (year is None or y == year)),
			None,
		)
		if pos is None:
			return m.group(0)
		out = month_fn(pos, m.group(1))
		if year:
			out += m.group(2) + year_fn(pos)
		return out

	parts = _TAG_RE.split(text)
	for k in range(0, len(parts), 2):
		seg = _MONTH_RE.sub(repl, parts[k])
		if old.months == 12:
			seg = re.sub(rf"\b{old.start.year}\b", lambda m: year_fn(0), seg)
		parts[k] = seg
	return "".join(parts)


def _match_case(word, original):
	if original.isupper():
		return word.upper()
	if original.islower():
		return word.lower()
	return word


def shift_text(text, old, new):
	"""Fallback: replace mentions of the `old` period with the `new` one."""
	if not new:
		return text
	new_months = _period_months(new)
	return _rewrite(
		text,
		old,
		lambda i, orig: _match_case(MESES[new_months[i].month - 1], orig),
		lambda i: str(new_months[i].year),
	)


def templatize_text(text, old):
	"""Turn mentions of the `old` period into Jinja placeholders."""
	if not old:
		return text
	last = old.months - 1

	def month_fn(i, orig):
		if old.months == 12:
			return orig
		var = "mes" if i == 0 else "mes_fim" if i == last else f"meses[{i}]"
		case = "|upper" if orig.isupper() else "|lower" if orig.islower() else ""
		return "{{ " + var + case + " }}"

	def year_fn(i):
		# A year next to a later month follows the period's end, so
		# "Agosto a Outubro 2026" still reads right for Novembro – Janeiro.
		return "{{ ano }}" if i == 0 or old.months == 12 else "{{ ano_fim }}"

	return _rewrite(text, old, month_fn, year_fn)


def detect_period(texts, months, near_date):
	"""Guess which period some text talks about, from the first month (or,
	for yearly, year) mentioned. A month without a year gets the year that
	puts it closest to `near_date`."""
	near = getdate(near_date or today())
	segments = [seg for text in texts if text for seg in _TAG_RE.split(text)[::2]]

	if months == 12:
		for seg in segments:
			m = re.search(r"\b(20\d{2})\b", seg)
			if m:
				return get_period(date(int(m.group(1)), 1, 1), months)

	for seg in segments:
		m = _MONTH_RE.search(seg)
		if m:
			month = _MONTH_NUMBER[m.group(1).lower()]
			year = cint(m.group(3))
			if not year:
				year = near.year
				if month - near.month > 6:
					year -= 1
				elif near.month - month > 6:
					year += 1
			return get_period(date(year, month, 1), months)
	return None


def render(template, context):
	return frappe.render_template(template, context)


# ---------------------------------------------------------------------------
# Applying to an invoice
# ---------------------------------------------------------------------------


def apply_billing_period(doc, reference_doc, ar):
	"""Set billing period, title and item descriptions on `doc`, a new
	invoice copied from `reference_doc` by Auto Repeat `ar`."""
	# The schedule date, not the posting date: an invoice issued ahead of
	# time (issue_auto_repeat_now) still bills the period it was due for.
	new = period_for_schedule(ar.next_schedule_date or doc.posting_date, ar.frequency, ar.billing_mode)
	if not new:
		return None

	doc.billing_period_start, doc.billing_period_end = new.start, new.end
	ctx = period_context(new)
	old = reference_period(
		reference_doc.get("billing_period_start"), reference_doc.posting_date, ar.frequency, ar.billing_mode
	)

	if ar.get("title_template"):
		doc.invoice_title = render(ar.title_template, ctx)
	else:
		doc.invoice_title = shift_text(doc.get("invoice_title"), old, new)

	templates = {
		cint(row.item_idx): row.description_template
		for row in ar.get("billing_descriptions") or []
		if row.description_template
	}
	for idx, item in enumerate(doc.items, 1):
		template = templates.get(idx)
		if template:
			item.description = render(
				template, {**ctx, "item_name": item.item_name, "item_code": item.item_code}
			)
		else:
			item.description = shift_text(item.description, old, new)

	return new


def apply_payment_terms(doc, reference_doc, ar):
	"""Give the new invoice a due date. due_date, payment_terms_template and
	payment_schedule are no_copy, and ERPNext's own on_recurring clears
	due_date, so without this it falls back to the customer's default terms,
	or to the posting date when there are none.

	In order: the Auto Repeat's Prazo de Pagamento (dias); the template
	invoice's Payment Terms Template (ERPNext rebuilds due date and schedule
	from it); the template invoice's gap between posting and due date.
	"""
	days = cint(ar.get("payment_days")) if ar else 0
	if days > 0:
		doc.due_date = add_days(doc.posting_date, days)
		return

	if reference_doc.get("payment_terms_template"):
		doc.payment_terms_template = reference_doc.payment_terms_template
		doc.due_date = None
		return

	if reference_doc.get("due_date") and reference_doc.get("posting_date"):
		days = date_diff(reference_doc.due_date, reference_doc.posting_date)
		if days > 0:
			doc.due_date = add_days(doc.posting_date, days)


def on_recurring(doc, method=None, reference_doc=None, auto_repeat_doc=None):
	"""doc_events hook: Auto Repeat calls this on the new invoice before it is
	inserted (and submitted, if Submit on Creation is set). Runs after
	ERPNext's SalesInvoice.on_recurring."""
	if reference_doc:
		apply_payment_terms(doc, reference_doc, auto_repeat_doc)

	if auto_repeat_doc and auto_repeat_doc.get("billing_mode"):
		apply_billing_period(doc, reference_doc, auto_repeat_doc)
	else:
		# Don't carry the template invoice's period over to the copy.
		doc.billing_period_start = doc.billing_period_end = None


def validate_auto_repeat(doc, method=None):
	"""Catch template mistakes when the Auto Repeat is saved, not when the
	invoice is generated unattended."""
	if doc.reference_doctype != "Sales Invoice" or not doc.get("billing_mode"):
		return

	if doc.frequency not in FREQ_MONTHS:
		frappe.throw(
			_("O Modo de Facturação só funciona com frequência Mensal, Trimestral, Semestral ou Anual.")
		)

	templates = [(_("Modelo do Título"), doc.get("title_template"))]
	for row in doc.get("billing_descriptions") or []:
		if not cint(row.item_idx):
			frappe.throw(_("Modelos das Descrições, linha {0}: indique a linha do item.").format(row.idx))
		templates.append((_("Modelo da Descrição, linha {0}").format(row.idx), row.description_template))

	env = frappe.get_jenv()
	for label, template in templates:
		if not template:
			continue
		try:
			ast = env.parse(template)
		except Exception as e:
			frappe.throw(_("Erro em {0}: {1}").format(label, e))
		unknown = meta.find_undeclared_variables(ast) - TEMPLATE_VARS - set(env.globals)
		if unknown:
			frappe.throw(
				_("Variável desconhecida em {0}: {1}. Variáveis disponíveis: {2}").format(
					label, ", ".join(sorted(unknown)), ", ".join(sorted(TEMPLATE_VARS))
				)
			)


def predict_title(row):
	"""Title the next invoice of an upcoming Auto Repeat row (Monitor de
	Facturas) will get. Falls back to the template invoice's title."""
	if not row.get("billing_mode"):
		return row.invoice_title
	try:
		new = period_for_schedule(row.next_schedule_date, row.frequency, row.billing_mode)
		if not new:
			return row.invoice_title
		if row.get("title_template"):
			return render(row.title_template, period_context(new))
		old = reference_period(row.ref_period_start, row.ref_posting_date, row.frequency, row.billing_mode)
		return shift_text(row.invoice_title, old, new)
	except Exception:
		return row.invoice_title


# ---------------------------------------------------------------------------
# Whitelisted helpers for the forms
# ---------------------------------------------------------------------------


def _check_invoice_permission(name, ptype="read"):
	if not name or not frappe.has_permission("Sales Invoice", ptype, doc=name):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


@frappe.whitelist()
def preview_next_invoice(doc):
	"""Render what the next invoice of an (unsaved) Auto Repeat will look like."""
	ar = frappe.get_doc(frappe.parse_json(doc))
	if ar.reference_doctype != "Sales Invoice" or not ar.get("billing_mode"):
		return None
	_check_invoice_permission(ar.reference_document)

	reference_doc = frappe.get_doc("Sales Invoice", ar.reference_document)
	new_doc = frappe.copy_doc(reference_doc)
	new_doc.posting_date = getdate(ar.next_schedule_date or ar.start_date or today())

	apply_payment_terms(new_doc, reference_doc, ar)
	if not new_doc.due_date:
		from erpnext.accounts.party import get_due_date

		new_doc.due_date = get_due_date(
			new_doc.posting_date,
			"Customer",
			new_doc.customer,
			new_doc.company,
			template_name=new_doc.get("payment_terms_template"),
		)

	try:
		period = apply_billing_period(new_doc, reference_doc, ar)
	except Exception as e:
		# Templates are often half-typed while the preview refreshes:
		# show the error inline instead of a popup.
		frappe.clear_messages()
		return {"error": str(e) or _("Erro no modelo.")}
	if not period:
		return None
	return {
		"posting_date": new_doc.posting_date,
		"due_date": new_doc.due_date,
		"periodo": period_label(period),
		"start": period.start,
		"end": period.end,
		"invoice_title": new_doc.invoice_title,
		"context": {
			**period_context(period),
			"item_name": new_doc.items[0].item_name if new_doc.items else "",
			"item_code": new_doc.items[0].item_code if new_doc.items else "",
		},
		"items": [
			{"idx": idx, "item_code": item.item_code, "description": item.description}
			for idx, item in enumerate(new_doc.items, 1)
		],
	}


@frappe.whitelist()
def get_template_suggestions(reference_document, frequency, billing_mode):
	"""Build title / description templates from the template invoice by
	turning its period mentions into placeholders."""
	_check_invoice_permission(reference_document)
	if frequency not in FREQ_MONTHS:
		frappe.throw(_("Escolha uma frequência Mensal, Trimestral, Semestral ou Anual."))

	reference_doc = frappe.get_doc("Sales Invoice", reference_document)
	old = reference_period(
		reference_doc.get("billing_period_start"), reference_doc.posting_date, frequency, billing_mode
	)
	return {
		"periodo": period_label(old),
		"title_template": templatize_text(reference_doc.get("invoice_title"), old),
		"rows": [
			{
				"item_idx": idx,
				"item_code": item.item_code,
				"description_template": templatize_text(item.description, old),
			}
			for idx, item in enumerate(reference_doc.items, 1)
		],
	}


@frappe.whitelist()
def get_manual_period(doc, frequency, month, year):
	"""For a manually created invoice: compute the chosen period and the
	title / descriptions with the previous period swapped for it."""
	si = frappe.get_doc(frappe.parse_json(doc))
	months = FREQ_MONTHS.get(frequency)
	if not months:
		frappe.throw(_("Frequência inválida."))

	new = get_period(date(cint(year), cint(month) or 1, 1), months)
	texts = [si.get("invoice_title")] + [item.description for item in si.items]
	if si.get("billing_period_start"):
		old = get_period(si.billing_period_start, months)
	else:
		old = detect_period(texts, months, si.posting_date)

	title = shift_text(si.get("invoice_title"), old, new)
	descriptions = [shift_text(item.description, old, new) for item in si.items]
	return {
		"billing_period_start": new.start,
		"billing_period_end": new.end,
		"periodo": period_label(new),
		"invoice_title": title,
		"descriptions": [{"idx": idx, "description": d} for idx, d in enumerate(descriptions, 1)],
		"changed": title != si.get("invoice_title")
		or any(d != item.description for d, item in zip(descriptions, si.items)),
	}
