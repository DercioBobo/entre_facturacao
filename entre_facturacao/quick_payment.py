import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

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


# ───────────────────── Bulk payment (same customer) ─────────────────────


def _load_invoice_list(invoices):
	if isinstance(invoices, str):
		invoices = frappe.parse_json(invoices)
	if not invoices or not isinstance(invoices, (list, tuple)):
		frappe.throw(_("Seleccione pelo menos uma factura."))
	# de-duplicate while preserving the order they were selected in
	return list(dict.fromkeys(invoices))


def _validate_bulk_invoices(invoices):
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"name": ["in", invoices]},
		fields=[
			"name",
			"customer",
			"customer_name",
			"company",
			"currency",
			"docstatus",
			"outstanding_amount",
			"due_date",
			"grand_total",
		],
	)
	by_name = {r.name: r for r in rows}
	missing = [i for i in invoices if i not in by_name]
	if missing:
		frappe.throw(_("Factura(s) não encontrada(s): {0}").format(", ".join(missing)))

	for name in invoices:
		if not frappe.has_permission("Sales Invoice", "read", doc=name):
			frappe.throw(_("Not permitted"), frappe.PermissionError)

	ordered = [by_name[i] for i in invoices]

	if len({r.customer for r in ordered}) > 1:
		frappe.throw(_("Todas as facturas seleccionadas têm de ser do mesmo cliente."))
	if len({r.company for r in ordered}) > 1:
		frappe.throw(_("Todas as facturas seleccionadas têm de ser da mesma empresa."))
	if len({r.currency for r in ordered}) > 1:
		frappe.throw(_("Todas as facturas seleccionadas têm de ter a mesma moeda."))

	for r in ordered:
		if r.docstatus != 1:
			frappe.throw(_("A factura {0} tem de estar submetida.").format(r.name))
		if flt(r.outstanding_amount) <= 0:
			frappe.throw(_("A factura {0} já não tem valor em dívida.").format(r.name))

	# oldest due date first, so a partial payment settles older debt first
	ordered.sort(key=lambda r: (getdate(r.due_date), r.name))
	return ordered


@frappe.whitelist()
def get_bulk_payment_defaults(invoices):
	"""Pre-fill data for the multi-invoice quick payment popup. All the
	given Sales Invoices must belong to the same customer/company/currency.
	"""
	rows = _validate_bulk_invoices(_load_invoice_list(invoices))
	total_outstanding = flt(sum(flt(r.outstanding_amount) for r in rows), 2)

	return {
		"customer": rows[0].customer,
		"customer_name": rows[0].customer_name,
		"company": rows[0].company,
		"currency": rows[0].currency,
		"count": len(rows),
		"total_outstanding": total_outstanding,
		"posting_date": nowdate(),
		"invoices": [
			{
				"invoice": r.name,
				"due_date": r.due_date,
				"outstanding_amount": flt(r.outstanding_amount, 2),
			}
			for r in rows
		],
	}


@frappe.whitelist()
def create_bulk_payment_entry(
	invoices,
	mode_of_payment=None,
	paid_amount=None,
	reference_no=None,
	reference_date=None,
	posting_date=None,
	remarks=None,
):
	"""Create and submit a single Payment Entry covering several Sales
	Invoices of the same customer. The paid amount is allocated across the
	invoices oldest-due-date first; any amount left over after the last
	invoice's outstanding is fully allocated is simply not applied further
	(it is capped against the total outstanding below, so this never
	produces an unallocated remainder).
	"""
	rows = _validate_bulk_invoices(_load_invoice_list(invoices))
	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	total_outstanding = flt(sum(flt(r.outstanding_amount) for r in rows), 2)
	paid_amount = flt(paid_amount)
	if paid_amount <= 0:
		frappe.throw(_("O valor pago deve ser maior que zero."))
	if paid_amount > total_outstanding + 0.01:
		frappe.throw(_("O valor pago não pode ser superior ao total em dívida."))

	company = rows[0].company
	bank_account = None
	if mode_of_payment:
		bank_account = get_bank_cash_account(mode_of_payment, company).get("account")

	# Map against the first (oldest) invoice to get correct party/bank
	# accounts and currency handling from ERPNext, then replace the single
	# auto-mapped reference with one row per selected invoice.
	pe = get_payment_entry(
		"Sales Invoice",
		rows[0].name,
		bank_account=bank_account,
		reference_date=reference_date or posting_date,
	)
	pe.set("references", [])

	remaining = paid_amount
	for r in rows:
		if remaining <= 0:
			break
		allocated = min(flt(r.outstanding_amount), remaining)
		pe.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": r.name,
				"due_date": r.due_date,
				"total_amount": r.grand_total,
				"outstanding_amount": r.outstanding_amount,
				"allocated_amount": allocated,
			},
		)
		remaining -= allocated

	pe.paid_amount = paid_amount
	pe.received_amount = paid_amount
	if mode_of_payment:
		pe.mode_of_payment = mode_of_payment
	pe.posting_date = posting_date or pe.posting_date
	pe.reference_no = reference_no or "-"
	if remarks:
		pe.remarks = remarks

	pe.insert()
	pe.submit()

	return {"name": pe.name, "count": len(pe.references)}
