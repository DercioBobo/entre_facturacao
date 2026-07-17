import frappe
from frappe import _
from frappe.utils import getdate, today


@frappe.whitelist()
def get_invoices(from_date=None, to_date=None, customer=None, status=None):
	"""Return filtered Sales Invoice rows and summary stats."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	conditions = ["si.docstatus = 1", "si.is_return = 0"]
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
		conditions.append("si.outstanding_amount <= 0")
	elif status == "Em Dívida":
		conditions.append("si.outstanding_amount > 0 AND si.due_date >= %(today_val)s")
		params["today_val"] = today_val
	elif status == "Vencida":
		conditions.append("si.outstanding_amount > 0 AND si.due_date < %(today_val)s")
		params["today_val"] = today_val

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
			si.outstanding_amount
		FROM `tabSales Invoice` si
		WHERE {where}
		ORDER BY si.posting_date DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	today_date = getdate(today_val)
	for r in rows:
		paid = float(r.grand_total or 0) - float(r.outstanding_amount or 0)
		r.paid = round(paid, 2)
		if float(r.outstanding_amount or 0) <= 0:
			r.display_status = "Paga"
		elif getdate(r.due_date) < today_date:
			r.display_status = "Vencida"
		else:
			r.display_status = "Em Dívida"

	overdue_rows = [r for r in rows if r.display_status == "Vencida"]
	total_invoiced = sum(float(r.grand_total or 0) for r in rows)
	total_paid = sum(r.paid for r in rows)
	total_outstanding = sum(float(r.outstanding_amount or 0) for r in rows)
	total_overdue = sum(float(r.outstanding_amount or 0) for r in overdue_rows)

	return {
		"rows": rows,
		"summary": {
			"count": len(rows),
			"total_invoiced": round(total_invoiced, 2),
			"total_paid": round(total_paid, 2),
			"total_outstanding": round(total_outstanding, 2),
			"total_overdue": round(total_overdue, 2),
			"overdue_count": len(overdue_rows),
		},
	}
