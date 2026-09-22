import frappe
from frappe import _
from frappe.utils import flt, nowdate

from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry
from erpnext.accounts.doctype.sales_invoice.sales_invoice import get_bank_cash_account


def _get_submitted_invoice(sales_invoice):
	if not frappe.has_permission("Sales Invoice", "read", doc=sales_invoice):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	si = frappe.get_cached_doc("Sales Invoice", sales_invoice)
	if si.docstatus != 1:
		frappe.throw(_("A factura tem de estar submetida."))
	if flt(si.outstanding_amount) <= 0:
		frappe.throw(_("Esta factura já não tem valor em dívida."))
	return si


@frappe.whitelist()
def get_quick_payment_defaults(sales_invoice):
	"""Minimal set of values to pre-fill the quick payment entry popup."""
	si = _get_submitted_invoice(sales_invoice)

	return {
		"customer": si.customer,
		"customer_name": si.customer_name,
		"company": si.company,
		"currency": si.currency,
		"outstanding_amount": flt(si.outstanding_amount, 2),
		"posting_date": nowdate(),
		"mode_of_payment": si.get("mode_of_payment") or "",
	}


@frappe.whitelist()
def create_quick_payment_entry(
	sales_invoice,
	mode_of_payment=None,
	paid_amount=None,
	reference_no=None,
	reference_date=None,
	posting_date=None,
	remarks=None,
):
	"""Create and submit a Payment Entry for a Sales Invoice from the quick
	payment popup (Monitor de Facturas / Sales Invoice), using only the
	handful of fields the popup exposes. Account resolution and currency
	handling are delegated to ERPNext's own get_payment_entry mapper so the
	result matches what the full Payment Entry form would produce.
	"""
	si = _get_submitted_invoice(sales_invoice)
	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	paid_amount = flt(paid_amount)
	if paid_amount <= 0:
		frappe.throw(_("O valor pago deve ser maior que zero."))
	if paid_amount > flt(si.outstanding_amount) + 0.01:
		frappe.throw(_("O valor pago não pode ser superior ao valor em dívida."))

	bank_account = None
	if mode_of_payment:
		bank_account = get_bank_cash_account(mode_of_payment, si.company).get("account")

	pe = get_payment_entry(
		"Sales Invoice",
		sales_invoice,
		party_amount=paid_amount,
		bank_account=bank_account,
		reference_date=reference_date or posting_date,
	)

	if mode_of_payment:
		pe.mode_of_payment = mode_of_payment
	pe.posting_date = posting_date or pe.posting_date
	pe.reference_no = reference_no or "-"
	if remarks:
		pe.remarks = remarks

	pe.insert()
	pe.submit()

	return {"name": pe.name}
