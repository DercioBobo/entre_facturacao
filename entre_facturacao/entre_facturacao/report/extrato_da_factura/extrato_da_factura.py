"""Extrato da Factura: lista todos os pagamentos (Payment Entry) alocados a
uma factura específica, com o saldo restante após cada pagamento, mais um
resumo do cabeçalho da factura (cliente, total, pago, saldo, estado)."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	if not filters.get("factura"):
		return columns, [], None, None, []
	data = get_data(filters)
	report_summary = get_report_summary(filters)
	return columns, data, None, None, report_summary


def get_columns():
	return [
		{"label": _("Data"), "fieldname": "data", "fieldtype": "Date", "width": 95},
		{"label": _("Pagamento"), "fieldname": "pagamento", "fieldtype": "Link", "options": "Payment Entry", "width": 160},
		{"label": _("Modo de Pagamento"), "fieldname": "modo_pagamento", "fieldtype": "Data", "width": 150},
		{"label": _("Valor Alocado"), "fieldname": "allocated_amount", "fieldtype": "Currency", "width": 130},
		{"label": _("Saldo Restante"), "fieldname": "saldo_restante", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	factura = filters["factura"]
	rows = frappe.db.sql(
		"""
		SELECT pe.name AS pagamento, pe.posting_date AS data, pe.mode_of_payment, per.allocated_amount
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		WHERE per.reference_doctype = 'Sales Invoice'
		  AND per.reference_name = %(factura)s
		  AND pe.docstatus = 1
		ORDER BY pe.posting_date ASC, pe.name ASC
		""",
		{"factura": factura},
		as_dict=True,
	)

	si = frappe.db.get_value("Sales Invoice", factura, "grand_total")
	saldo = flt(si)
	for r in rows:
		r["data"] = getdate(r.data)
		r["modo_pagamento"] = r.mode_of_payment or ""
		saldo = flt(saldo - r.allocated_amount)
		r["saldo_restante"] = saldo

	return rows


def get_report_summary(filters):
	si = frappe.db.get_value(
		"Sales Invoice",
		filters["factura"],
		["customer_name", "customer", "grand_total", "outstanding_amount", "due_date"],
		as_dict=True,
	)
	if not si:
		return []

	total_pago = flt(si.grand_total) - flt(si.outstanding_amount)
	if flt(si.outstanding_amount) <= 0:
		estado, indicator = _("Paga"), "Green"
	elif si.due_date and getdate(si.due_date) < getdate():
		estado, indicator = _("Vencida"), "Red"
	else:
		estado, indicator = _("Em Dívida"), "Orange"

	return [
		{"value": si.customer_name or si.customer, "label": _("Cliente"), "datatype": "Data"},
		{"value": flt(si.grand_total), "label": _("Total da Factura"), "datatype": "Currency"},
		{"value": flt(total_pago), "label": _("Total Pago"), "datatype": "Currency"},
		{"value": flt(si.outstanding_amount), "label": _("Saldo em Aberto"), "datatype": "Currency"},
		{"value": estado, "label": _("Estado"), "datatype": "Data", "indicator": indicator},
	]
