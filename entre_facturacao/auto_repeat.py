import frappe
from frappe import _
from frappe.utils import add_months, cint, get_first_day, get_last_day, getdate


@frappe.whitelist()
def get_conflicting_auto_repeat(sales_invoice):
	"""Find an active, Monthly Auto Repeat for the same customer whose next
	invoice is scheduled within the same month as the given Sales Invoice.

	Used to warn a user who manually creates an invoice that an automatic
	one is also due this month, so they can skip the duplicate.
	"""
	if not frappe.has_permission("Sales Invoice", "read", doc=sales_invoice):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	si = frappe.db.get_value(
		"Sales Invoice", sales_invoice, ["customer", "posting_date", "auto_repeat"], as_dict=True
	)
	if not si or si.auto_repeat:
		return None

	month_start = get_first_day(si.posting_date)
	month_end = get_last_day(si.posting_date)

	rows = frappe.db.sql(
		"""
		SELECT ar.name, ar.next_schedule_date
		FROM `tabAuto Repeat` ar
		INNER JOIN `tabSales Invoice` ref ON ref.name = ar.reference_document
		WHERE ar.reference_doctype = 'Sales Invoice'
		  AND ar.docstatus = 1
		  AND ar.disabled = 0
		  AND ar.frequency = 'Monthly'
		  AND ref.customer = %(customer)s
		  AND ar.next_schedule_date BETWEEN %(start)s AND %(end)s
		LIMIT 1
		""",
		{"customer": si.customer, "start": month_start, "end": month_end},
		as_dict=True,
	)
	return rows[0] if rows else None


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
