import frappe
from frappe import _
from frappe.utils import cint, getdate, today


@frappe.whitelist()
def get_invoices(from_date=None, to_date=None, customer=None, status=None, include_drafts=0):
	"""Return filtered Sales Invoice rows and summary stats."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	conditions = ["si.is_return = 0"]
	params = {}

	if from_date:
		conditions.append("si.posting_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("si.posting_date <= %(to_date)s")
		params["to_date"] = to_date
	if customer:
		conditions.append("si.customer = %(customer)s")
		params["customer"] = customer

	today_val = today()
	if status == "Paga":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount <= 0")
	elif status == "Em Dívida":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount > 0 AND si.due_date >= %(today_val)s")
		params["today_val"] = today_val
	elif status == "Vencida":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount > 0 AND si.due_date < %(today_val)s")
		params["today_val"] = today_val
	elif status == "Rascunho":
		conditions.append("si.docstatus = 0")
	elif cint(include_drafts):
		conditions.append("si.docstatus IN (0, 1)")
	else:
		conditions.append("si.docstatus = 1")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			si.name               AS invoice,
			si.customer,
			si.customer_name,
			si.posting_date,
			si.due_date,
			si.grand_total,
			si.outstanding_amount,
			si.docstatus
		FROM `tabSales Invoice` si
		WHERE {where}
		ORDER BY si.posting_date DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	today_date = getdate(today_val)
	posted_rows = [r for r in rows if r.docstatus == 1]
	draft_rows = [r for r in rows if r.docstatus == 0]

	for r in posted_rows:
		paid = float(r.grand_total or 0) - float(r.outstanding_amount or 0)
		r.paid = round(paid, 2)
		if float(r.outstanding_amount or 0) <= 0:
			r.display_status = "Paga"
		elif getdate(r.due_date) < today_date:
			r.display_status = "Vencida"
		else:
			r.display_status = "Em Dívida"

	for r in draft_rows:
		r.display_status = "Rascunho"
		r.paid = 0.0

	overdue_rows = [r for r in posted_rows if r.display_status == "Vencida"]
	total_invoiced = sum(float(r.grand_total or 0) for r in posted_rows)
	total_paid = sum(r.paid for r in posted_rows)
	total_outstanding = sum(float(r.outstanding_amount or 0) for r in posted_rows)
	total_overdue = sum(float(r.outstanding_amount or 0) for r in overdue_rows)

	return {
		"rows": rows,
		"summary": {
			"count": len(posted_rows),
			"draft_count": len(draft_rows),
			"total_invoiced": round(total_invoiced, 2),
			"total_paid": round(total_paid, 2),
			"total_outstanding": round(total_outstanding, 2),
			"total_overdue": round(total_overdue, 2),
			"overdue_count": len(overdue_rows),
		},
	}


@frappe.whitelist()
def get_upcoming_invoices(from_date=None, to_date=None, customer=None, status=None):
	"""Return upcoming Auto Repeat-generated Sales Invoices and summary stats."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Auto Repeat", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	conditions = ["ar.reference_doctype = 'Sales Invoice'", "ar.docstatus = 1"]
	params = {}

	if from_date:
		conditions.append("ar.next_schedule_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("ar.next_schedule_date <= %(to_date)s")
		params["to_date"] = to_date
	if customer:
		conditions.append("si.customer = %(customer)s")
		params["customer"] = customer

	today_val = today()
	if status == "Activo":
		conditions.append("ar.disabled = 0 AND (ar.end_date IS NULL OR ar.end_date >= %(today_val)s)")
		params["today_val"] = today_val
	elif status == "Concluído":
		conditions.append("ar.disabled = 0 AND ar.end_date IS NOT NULL AND ar.end_date < %(today_val)s")
		params["today_val"] = today_val
	elif status == "Desactivado":
		conditions.append("ar.disabled = 1")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			ar.name                AS auto_repeat,
			ar.reference_document  AS invoice_ref,
			ar.next_schedule_date,
			ar.frequency,
			ar.disabled,
			ar.end_date,
			si.customer,
			si.customer_name,
			si.grand_total
		FROM `tabAuto Repeat` ar
		INNER JOIN `tabSales Invoice` si ON si.name = ar.reference_document
		WHERE {where}
		ORDER BY ar.next_schedule_date ASC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	today_date = getdate(today_val)
	for r in rows:
		if r.disabled:
			r.display_status = "Desactivado"
		elif r.end_date and getdate(r.end_date) < today_date:
			r.display_status = "Concluído"
		else:
			r.display_status = "Activo"

	total_expected = sum(float(r.grand_total or 0) for r in rows)
	next_dates = [getdate(r.next_schedule_date) for r in rows if r.next_schedule_date]

	return {
		"rows": rows,
		"summary": {
			"count": len(rows),
			"total_expected": round(total_expected, 2),
			"next_date": min(next_dates).isoformat() if next_dates else None,
		},
	}
