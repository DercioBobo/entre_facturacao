"""Agenda de Factura: a Sales Invoice to be issued on a future date.

Nothing is created in Sales Invoice until the day: the agenda only holds the
customer, items and dates. On the scheduled date the `issue_due` job builds a
normal Sales Invoice from it (taking the next number of its series on that
day), submits it and links it back. A failure leaves the agenda in "Erro" and
notifies whoever created it.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, flt, getdate, now_datetime, strip_html, today

from entre_facturacao.billing_period import set_explicit_due_date

SCHEDULED = "Agendada"
ISSUED = "Emitida"
ERROR = "Erro"
CANCELLED = "Cancelada"


class AgendadeFactura(Document):
	def validate(self):
		before = self.get_doc_before_save()
		if before and before.status in (ISSUED, CANCELLED):
			frappe.throw(_("Esta agenda está {0} e já não pode ser alterada.").format(_(before.status)))

		if self.billing_period_start and not self.billing_period_end:
			self.billing_period_end = frappe.utils.get_last_day(self.billing_period_start)
		if self.billing_period_end and not self.billing_period_start:
			frappe.throw(_("Indique o início do Período de Facturação."))
		if self.billing_period_start and getdate(self.billing_period_end) < getdate(self.billing_period_start):
			frappe.throw(_("O fim do Período de Facturação é anterior ao início."))

		for row in self.items:
			if flt(row.qty) <= 0:
				frappe.throw(_("Itens, linha {0}: a quantidade tem de ser maior que zero.").format(row.idx))

		# Saving again after an error means it was fixed: try again on schedule.
		if self.status == ERROR:
			self.status = SCHEDULED
			self.error_message = None

		series = invoice_naming_series()
		if self.invoice_naming_series and self.invoice_naming_series not in series:
			frappe.throw(
				_("Série da Factura inválida: {0}. Séries disponíveis: {1}").format(
					self.invoice_naming_series, ", ".join(series)
				)
			)

		self.set_totals()

	def on_trash(self):
		if self.status == ISSUED:
			frappe.throw(_("Não é possível apagar uma agenda já emitida."))

	def set_totals(self):
		"""Estimated totals, from the same invoice the agenda will issue.
		Building it now also surfaces missing accounts, prices, etc. at save
		time instead of on the scheduled day."""
		if not (self.customer and self.company and self.items):
			return  # mandatory check reports it
		si = self.make_sales_invoice(self.scheduled_date or today())
		self.currency = si.currency
		self.net_total = si.net_total
		self.total_taxes_and_charges = si.total_taxes_and_charges
		self.grand_total = si.grand_total
		for row, item in zip(self.items, si.items):
			row.amount = item.amount

	def make_sales_invoice(self, posting_date):
		"""The (unsaved) Sales Invoice this agenda issues on `posting_date`."""
		si = frappe.new_doc("Sales Invoice")
		if self.invoice_naming_series:
			si.naming_series = self.invoice_naming_series
		si.company = self.company
		si.customer = self.customer
		si.posting_date = getdate(posting_date)
		si.set_posting_time = 1
		si.invoice_title = self.invoice_title
		si.billing_period_start = self.billing_period_start
		si.billing_period_end = self.billing_period_end
		si.agenda_de_factura = self.name if not self.is_new() else None
		if self.taxes_and_charges:
			si.taxes_and_charges = self.taxes_and_charges

		for row in self.items:
			si.append(
				"items",
				{
					"item_code": row.item_code,
					"qty": flt(row.qty) or 1,
					# None lets ERPNext fill in the price list rate / item description.
					"rate": flt(row.rate) or None,
					"description": row.description or None,
				},
			)

		si.set_missing_values()
		days = cint(self.payment_days)
		if days > 0:
			set_explicit_due_date(si, add_days(si.posting_date, days))
		if not si.get("taxes"):
			si.set_taxes()
		si.calculate_taxes_and_totals()
		return si

	def issue(self):
		"""Create (and submit) the Sales Invoice. It is dated today, not the
		scheduled date, so a late run never backdates it behind invoices
		issued in the meantime."""
		if self.status not in (SCHEDULED, ERROR):
			frappe.throw(_("Esta agenda está {0}.").format(_(self.status)))

		si = self.make_sales_invoice(today())
		si.agenda_de_factura = self.name
		si.insert()
		if cint(self.submit_on_creation):
			si.submit()

		self.db_set(
			{
				"status": ISSUED,
				"sales_invoice": si.name,
				"issued_on": now_datetime(),
				"error_message": None,
			}
		)
		return si

	@frappe.whitelist()
	def issue_now(self):
		self.check_permission("write")
		si = self.issue()
		return si.name

	@frappe.whitelist()
	def cancel_schedule(self):
		self.check_permission("write")
		if self.status not in (SCHEDULED, ERROR):
			frappe.throw(_("Esta agenda está {0}.").format(_(self.status)))
		self.db_set("status", CANCELLED)

	@frappe.whitelist()
	def reactivate(self):
		self.check_permission("write")
		if self.status != CANCELLED:
			frappe.throw(_("Só uma agenda cancelada pode ser reactivada."))
		self.db_set({"status": SCHEDULED, "error_message": None})


# ---------------------------------------------------------------------------
# Naming series
# ---------------------------------------------------------------------------


def invoice_naming_series():
	"""The Sales Invoice naming series, as configured (property setters
	included)."""
	df = frappe.get_meta("Sales Invoice").get_field("naming_series")
	return [s.strip() for s in (df.options or "").split("\n") if s.strip()] if df else []


@frappe.whitelist()
def get_invoice_naming_series():
	if not frappe.has_permission("Agenda de Factura", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	df = frappe.get_meta("Sales Invoice").get_field("naming_series")
	return {"options": invoice_naming_series(), "default": df.default if df else None}


def predict_invoice_name(si):
	"""The number `si` would get if it were saved now. Only a forecast: any
	invoice issued in the meantime takes it first."""
	if not si.get("naming_series"):
		return None
	try:
		from frappe.model.naming import NamingSeries

		names = NamingSeries(si.naming_series).get_preview(doc=si)
		return names[0] if names else None
	except Exception:
		return None


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def issue_due():
	"""Hourly: issue every agenda whose date has come. Each one is committed
	on its own, so one failure doesn't hold back the others."""
	names = frappe.get_all(
		"Agenda de Factura",
		filters={"status": SCHEDULED, "scheduled_date": ["<=", today()]},
		order_by="scheduled_date asc, creation asc",
		pluck="name",
	)
	for name in names:
		_issue_one(name)


def _issue_one(name):
	try:
		doc = frappe.get_doc("Agenda de Factura", name, for_update=True)
		if doc.status != SCHEDULED:
			return
		si = doc.issue()
		frappe.db.commit()
	except Exception as e:
		frappe.db.rollback()
		message = strip_html(str(e)) or _("Erro desconhecido.")
		frappe.clear_messages()
		frappe.db.set_value("Agenda de Factura", name, {"status": ERROR, "error_message": message})
		frappe.log_error(
			title=_("Agenda de Factura {0}: falha na emissão").format(name),
			reference_doctype="Agenda de Factura",
			reference_name=name,
		)
		_notify(name, _("Agenda {0}: a factura não foi emitida").format(name), message)
		frappe.db.commit()
		return

	_notify(
		name,
		_("Agenda {0}: factura {1} emitida").format(name, si.name),
		_("Cliente: {0}. Total: {1}").format(
			si.customer_name, frappe.utils.fmt_money(si.grand_total, currency=si.currency)
		),
	)
	frappe.db.commit()


def _notify(name, subject, content):
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	owner = frappe.db.get_value("Agenda de Factura", name, "owner")
	if not owner or owner in ("Administrator", "Guest"):
		return
	enqueue_create_notification(
		owner,
		{
			"type": "Alert",
			"document_type": "Agenda de Factura",
			"document_name": name,
			"subject": subject,
			"email_content": content,
		},
	)


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------


@frappe.whitelist()
def get_preview(doc, print_format=None):
	"""Render the invoice an (unsaved) agenda will issue with a Sales Invoice
	print format, as it would look on the scheduled date."""
	from frappe.www.printview import (
		get_print_format_doc,
		get_print_style,
		get_rendered_template,
		set_link_titles,
	)

	agenda = frappe.get_doc(frappe.parse_json(doc))
	if not frappe.has_permission("Agenda de Factura", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Sales Invoice", "print"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	si = agenda.make_sales_invoice(agenda.scheduled_date or today())
	si.name = predict_invoice_name(si) or _("Pré-visualização")

	print_format = print_format or frappe.get_meta("Sales Invoice").default_print_format or "Standard"
	# Same steps as printview.get_html_and_style, which only takes a saved
	# doc's name or JSON (and checks permission on it). The invoice is
	# unsaved and a draft: permission was checked above.
	print_format_doc = get_print_format_doc(print_format, meta=si.meta)
	set_link_titles(si)
	frappe.flags.ignore_print_permissions = True
	try:
		html = get_rendered_template(doc=si, print_format=print_format_doc, meta=si.meta)
	except frappe.TemplateNotFoundError:
		frappe.clear_last_message()
		html = None
	finally:
		frappe.flags.ignore_print_permissions = False

	return {
		"html": html,
		"style": get_print_style(print_format=print_format_doc),
		"print_format": print_format,
		"posting_date": si.posting_date,
		"due_date": si.due_date,
		"currency": si.currency,
		"net_total": si.net_total,
		"total_taxes_and_charges": si.total_taxes_and_charges,
		"grand_total": si.grand_total,
		"invoice_name": si.name,
		"naming_series": si.naming_series,
	}
