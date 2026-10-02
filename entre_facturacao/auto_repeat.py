import frappe
from frappe import _
from frappe.utils import add_months, cint, get_first_day, get_last_day, getdate, today

from entre_facturacao.billing_period import apply_payment_terms, period_for_schedule, period_label, periods_overlap


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
