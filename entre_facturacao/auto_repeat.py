import frappe
from frappe import _
from frappe.utils import add_months, cint, get_first_day, get_last_day, getdate, today

from entre_facturacao.billing_period import (
	FREQ_MONTHS,
	apply_payment_terms,
	get_template_suggestions,
	period_for_schedule,
	period_label,
	periods_overlap,
)


@frappe.whitelist()
def get_conflicting_auto_repeat(sales_invoice):
	"""Find an active, Monthly Auto Repeat for the same customer whose next
	invoice bills the same period as the given Sales Invoice.

	Used to warn a user who manually creates an invoice that an automatic
	one is also due for that period, so they can skip the duplicate.

	When both sides know their billing period (the invoice has
	billing_period_start, the Auto Repeat has a Modo de Facturação), the
	periods are compared; otherwise it falls back to comparing the invoice's
	posting month with the Auto Repeat's schedule month.
	"""
	if not frappe.has_permission("Sales Invoice", "read", doc=sales_invoice):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	si = frappe.db.get_value(
		"Sales Invoice",
		sales_invoice,
		["customer", "posting_date", "auto_repeat", "billing_period_start", "billing_period_end"],
		as_dict=True,
	)
	if not si or si.auto_repeat:
		return None

	rows = frappe.db.sql(
		"""
		SELECT ar.name, ar.next_schedule_date, ar.frequency, ar.billing_mode
		FROM `tabAuto Repeat` ar
		INNER JOIN `tabSales Invoice` ref ON ref.name = ar.reference_document
		WHERE ar.reference_doctype = 'Sales Invoice'
		  AND ar.disabled = 0
		  AND ar.frequency = 'Monthly'
		  AND ref.customer = %(customer)s
		  AND ar.next_schedule_date IS NOT NULL
		ORDER BY ar.next_schedule_date
		""",
		{"customer": si.customer},
		as_dict=True,
	)

	si_period = None
	if si.billing_period_start:
		si_period = frappe._dict(
			start=getdate(si.billing_period_start),
			end=getdate(si.billing_period_end or si.billing_period_start),
		)
	month_start = get_first_day(si.posting_date)
	month_end = get_last_day(si.posting_date)

	for row in rows:
		ar_period = period_for_schedule(row.next_schedule_date, row.frequency, row.billing_mode)
		if si_period and row.billing_mode and ar_period:
			if periods_overlap(si_period, ar_period):
				return {
					"name": row.name,
					"next_schedule_date": row.next_schedule_date,
					"periodo": period_label(ar_period),
				}
		elif month_start <= getdate(row.next_schedule_date) <= month_end:
			return {"name": row.name, "next_schedule_date": row.next_schedule_date}
	return None


@frappe.whitelist()
def skip_auto_repeat_this_month(auto_repeat):
	"""Push a Monthly Auto Repeat's next_schedule_date forward by one month,
	so it doesn't also fire for a period already covered by a manual invoice.
	"""
	doc = frappe.get_doc("Auto Repeat", auto_repeat)
	if doc.reference_doctype != "Sales Invoice":
		frappe.throw(_("Invalid request"))
	if not frappe.has_permission("Sales Invoice", "write", doc=doc.reference_document):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	new_date = add_months(getdate(doc.next_schedule_date), 1)
	doc.db_set("next_schedule_date", new_date)
	return {"next_schedule_date": new_date.isoformat()}


@frappe.whitelist()
def toggle_auto_repeat(auto_repeat, disabled):
	"""Pause or resume a Monthly Auto Repeat from the Monitor page's
	Próximas Facturas tab, without needing to open the raw Auto Repeat form.
	"""
	doc = frappe.get_doc("Auto Repeat", auto_repeat)
	if doc.reference_doctype != "Sales Invoice":
		frappe.throw(_("Invalid request"))
	if not frappe.has_permission("Sales Invoice", "write", doc=doc.reference_document):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	doc.db_set("disabled", cint(disabled))
	return {"disabled": cint(disabled)}


def _get_issuable_auto_repeat(auto_repeat, for_update=False):
	doc = frappe.get_doc("Auto Repeat", auto_repeat, for_update=for_update)
	if doc.reference_doctype != "Sales Invoice":
		frappe.throw(_("Invalid request"))
	if not frappe.has_permission("Sales Invoice", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Sales Invoice", "write", doc=doc.reference_document):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if doc.disabled:
		frappe.throw(_("Esta repetição está desactivada."))
	if not doc.next_schedule_date:
		frappe.throw(_("Esta repetição não tem próxima data."))
	return doc


@frappe.whitelist()
def get_issue_now_info(auto_repeat):
	"""What issue_auto_repeat_now will do, for the confirmation dialog."""
	doc = _get_issuable_auto_repeat(auto_repeat)
	schedule_date = getdate(doc.next_schedule_date)
	period = period_for_schedule(schedule_date, doc.frequency, doc.billing_mode) if doc.billing_mode else None
	return {
		"schedule_date": schedule_date,
		"next_schedule_date": doc.get_next_schedule_date(schedule_date=schedule_date),
		"periodo": period_label(period) if period else None,
		"submit_on_creation": doc.submit_on_creation,
	}


@frappe.whitelist()
def issue_auto_repeat_now(auto_repeat):
	"""Issue an Auto Repeat's next invoice today, ahead of its schedule (the
	customer wants to pay now), then move the schedule on one cycle exactly
	as if it had run on its date: due 04-10-2026 yearly, issued 02-04-2026,
	next becomes 04-10-2027.

	The invoice is dated today but bills the period of the date it was due
	for (see apply_billing_period).
	"""
	doc = _get_issuable_auto_repeat(auto_repeat, for_update=True)
	schedule_date = getdate(doc.next_schedule_date)

	# Same steps as AutoRepeat.make_new_document, but dated today.
	reference_doc = frappe.get_doc(doc.reference_doctype, doc.reference_document)
	new_doc = frappe.copy_doc(reference_doc, ignore_no_copy=False)
	doc.update_doc(new_doc, reference_doc)  # runs on_recurring with the schedule date

	new_doc.posting_date = getdate(today())
	new_doc.set_posting_time = 1
	# Due date follows the real posting date.
	new_doc.due_date = None
	apply_payment_terms(new_doc, reference_doc, doc)

	new_doc.insert()
	if doc.submit_on_creation:
		new_doc.submit()

	next_date = doc.get_next_schedule_date(schedule_date=schedule_date)
	doc.db_set("next_schedule_date", next_date)

	if doc.notify_by_email and doc.recipients:
		try:
			doc.send_notification(new_doc)
		except Exception:
			frappe.log_error(
				title=_("Auto Repeat {0}: falha no envio do email").format(doc.name),
				reference_doctype="Auto Repeat",
				reference_name=doc.name,
			)

	return {"invoice": new_doc.name, "next_schedule_date": next_date}


@frappe.whitelist()
def create_auto_repeat_from_invoice(
	sales_invoice,
	frequency,
	start_date,
	end_date=None,
	billing_mode=None,
	payment_days=None,
	submit_on_creation=0,
	notify_by_email=0,
	recipients=None,
):
	"""Create an Auto Repeat with the given invoice as its template, straight
	from the invoice form. With a Modo de Facturação, the title / description
	templates are filled in from the invoice like the Auto Repeat's "Copiar
	descrições da factura modelo" button does."""
	si = frappe.get_doc("Sales Invoice", sales_invoice)
	si.check_permission("write")
	if si.docstatus == 2:
		frappe.throw(_("Não é possível repetir uma factura cancelada."))
	if si.get("is_return"):
		frappe.throw(_("Não é possível repetir uma nota de crédito."))
	if si.get("auto_repeat"):
		frappe.throw(_("Esta factura já tem a repetição automática {0}.").format(si.auto_repeat))

	months = FREQ_MONTHS.get(frequency)
	if not months:
		frappe.throw(_("Frequência inválida."))
	first_date = getdate(start_date)
	if first_date < getdate(today()):
		frappe.throw(_("A primeira factura não pode ser anterior a hoje."))

	ar = frappe.new_doc("Auto Repeat")
	ar.update(
		{
			"reference_doctype": "Sales Invoice",
			"reference_document": si.name,
			"frequency": frequency,
			# Frappe's first run is one cycle after start_date.
			"start_date": add_months(first_date, -months),
			"repeat_on_day": first_date.day,
			"end_date": end_date or None,
			"submit_on_creation": cint(submit_on_creation),
			"notify_by_email": cint(notify_by_email),
			"recipients": recipients if cint(notify_by_email) else None,
			"billing_mode": billing_mode or None,
			"payment_days": cint(payment_days) or None,
		}
	)

	if billing_mode:
		suggestions = get_template_suggestions(si.name, frequency, billing_mode)
		# Only texts that mention the period become templates; the rest are
		# copied from the invoice as they are, so later edits to it still count.
		if "{{" in (suggestions["title_template"] or ""):
			ar.title_template = suggestions["title_template"]
		for row in suggestions["rows"]:
			if "{{" in (row["description_template"] or ""):
				ar.append("billing_descriptions", row)

	ar.insert()
	return {"name": ar.name, "next_schedule_date": ar.next_schedule_date}


# Fields Frappe's AutoRepeat.set_dates derives next_schedule_date from.
SCHEDULE_FIELDS = ("start_date", "frequency", "repeat_on_day", "repeat_on_last_day", "disabled")


def preserve_next_schedule_date(doc, method=None):
	"""doc_events validate hook. Frappe recomputes next_schedule_date from
	start_date on every save, which would undo a date moved by hand
	(set_next_schedule_date, skip_auto_repeat_this_month,
	issue_auto_repeat_now) and could issue a period twice. Keep the stored
	date unless the schedule itself was changed."""
	prev = doc.get_doc_before_save()
	if doc.is_new() or not prev or doc.disabled or not prev.next_schedule_date:
		return
	if any(doc.get(f) != prev.get(f) for f in SCHEDULE_FIELDS):
		return
	kept = getdate(prev.next_schedule_date)
	if kept < getdate(today()) or (doc.end_date and kept > getdate(doc.end_date)):
		return
	doc.next_schedule_date = kept


def _get_editable_auto_repeat(auto_repeat):
	doc = frappe.get_doc("Auto Repeat", auto_repeat)
	if doc.reference_doctype != "Sales Invoice":
		frappe.throw(_("Invalid request"))
	if not frappe.has_permission("Sales Invoice", "write", doc=doc.reference_document):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	doc.check_permission("write")
	return doc


def _period_info(doc, schedule_date):
	if not schedule_date or not doc.get("billing_mode"):
		return None
	period = period_for_schedule(schedule_date, doc.frequency, doc.billing_mode)
	return period_label(period) if period else None


@frappe.whitelist()
def get_next_schedule_date_info(auto_repeat, next_schedule_date=None):
	"""For the "Alterar Próxima Data" dialog: the billed period of the
	current and of the proposed date."""
	doc = _get_editable_auto_repeat(auto_repeat)
	return {
		"current_date": doc.next_schedule_date,
		"current_periodo": _period_info(doc, doc.next_schedule_date),
		"periodo": _period_info(doc, next_schedule_date),
		"month_based": doc.frequency in FREQ_MONTHS,
	}


@frappe.whitelist()
def set_next_schedule_date(auto_repeat, next_schedule_date, shift_following=0):
	"""Move an Auto Repeat's next invoice to another date.

	Frappe only issues on the exact next_schedule_date, so it can't be in
	the past. By default only this invoice moves: the cycles after it stay
	on the original day (due on the 2nd, moved to the 10th → next one on
	the 2nd again). With shift_following, the schedule itself moves so later
	invoices follow the new date.
	"""
	doc = _get_editable_auto_repeat(auto_repeat)
	if doc.disabled:
		frappe.throw(_("Esta repetição está desactivada."))

	new_date = getdate(next_schedule_date)
	if new_date < getdate(today()):
		frappe.throw(_("A próxima data não pode ser anterior a hoje."))
	if doc.end_date and new_date > getdate(doc.end_date):
		frappe.throw(_("A próxima data não pode ser posterior à Data de Fim ({0}).").format(doc.end_date))

	months = FREQ_MONTHS.get(doc.frequency)
	if cint(shift_following) and months:
		# Next cycle = start_date + n cycles, on repeat_on_day if set.
		doc.start_date = add_months(new_date, -months)
		doc.repeat_on_day = new_date.day
		doc.repeat_on_last_day = 0
		doc.save()
	# Daily / Weekly cycles count from the last schedule date, so later
	# invoices follow the new date anyway.
	doc.db_set("next_schedule_date", new_date)

	following = getdate(doc.get_next_schedule_date(schedule_date=new_date, for_full_schedule=True))
	return {
		"next_schedule_date": new_date,
		"following_date": following if not doc.end_date or following <= getdate(doc.end_date) else None,
		"periodo": _period_info(doc, new_date),
	}
