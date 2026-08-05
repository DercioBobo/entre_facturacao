"""Extrato de Cliente Simplificado: mostra, para cada pagamento recebido de
um cliente, a que factura(s) foi alocado e em que valor - dando visibilidade
sobre a distribuição de pagamentos que cobrem várias facturas ou que pagam
apenas parte de uma factura."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

ADIANTAMENTO = _("Adiantamento não alocado")


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	if not filters.get("cliente"):
		return columns, []
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": _("Data"), "fieldname": "data", "fieldtype": "Date", "width": 95},
		{
			"label": _("Pagamento"),
			"fieldname": "pagamento",
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 120,
		},
		{"label": _("Modo de Pagamento"), "fieldname": "modo_pagamento", "fieldtype": "Data", "width": 130},
		{
			"label": _("Factura"),
			"fieldname": "factura",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 120,
		},
		{"label": _("Descrição"), "fieldname": "descricao", "fieldtype": "Data", "width": 200},
		{"label": _("Valor da Factura"), "fieldname": "valor_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Valor Alocado"), "fieldname": "valor_alocado", "fieldtype": "Currency", "width": 120},
		{"label": _("Saldo da Factura"), "fieldname": "saldo_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Estado da Factura"), "fieldname": "estado", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	cliente = filters["cliente"]
	empresa = filters.get("empresa")

	linhas = get_alocacoes(cliente, empresa) + get_adiantamentos(cliente, empresa)
	linhas.sort(key=lambda l: (l["data"], l["pagamento"]))

	data_inicio = getdate(filters["data_inicio"]) if filters.get("data_inicio") else None
	data_fim = getdate(filters["data_fim"]) if filters.get("data_fim") else None
	if data_inicio:
		linhas = [l for l in linhas if l["data"] >= data_inicio]
	if data_fim:
		linhas = [l for l in linhas if l["data"] <= data_fim]

	estados = filters.get("estado")
	if estados:
		if isinstance(estados, str):
			estados = frappe.parse_json(estados) if estados.startswith("[") else [estados]
		if estados:
			linhas = [l for l in linhas if not l["factura"] or l["estado"] in estados]

	linhas.sort(key=lambda l: l["data"], reverse=True)
	return linhas


def get_alocacoes(cliente, empresa=None):
	conditions = [
		"pe.party_type = 'Customer'",
		"pe.party = %(cliente)s",
		"pe.docstatus = 1",
		"per.reference_doctype = 'Sales Invoice'",
	]
	params = {"cliente": cliente}
	if empresa:
		conditions.append("pe.company = %(empresa)s")
		params["empresa"] = empresa

	rows = frappe.db.sql(
		f"""
		SELECT pe.name AS pagamento, pe.posting_date, pe.mode_of_payment,
			per.allocated_amount, si.name AS factura, si.invoice_title,
			si.grand_total, si.outstanding_amount, si.due_date
		FROM `tabPayment Entry Reference` per
		INNER JOIN `tabPayment Entry` pe ON pe.name = per.parent
		INNER JOIN `tabSales Invoice` si ON si.name = per.reference_name
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	today_date = getdate()
	linhas = []
	for r in rows:
		if flt(r.outstanding_amount) <= 0:
			estado = _("Paga")
		elif getdate(r.due_date) < today_date:
			estado = _("Vencida")
		else:
			estado = _("Em Dívida")

		linhas.append(
			{
				"data": getdate(r.posting_date),
				"pagamento": r.pagamento,
				"modo_pagamento": r.mode_of_payment or "",
				"factura": r.factura,
				"descricao": r.invoice_title or _("Factura Nº {0}").format(r.factura),
				"valor_factura": flt(r.grand_total),
				"valor_alocado": flt(r.allocated_amount),
				"saldo_factura": flt(r.outstanding_amount),
				"estado": estado,
			}
		)
	return linhas


def get_adiantamentos(cliente, empresa=None):
	conditions = [
		"pe.party_type = 'Customer'",
		"pe.party = %(cliente)s",
		"pe.docstatus = 1",
		"pe.unallocated_amount > 0",
	]
	params = {"cliente": cliente}
	if empresa:
		conditions.append("pe.company = %(empresa)s")
		params["empresa"] = empresa

	rows = frappe.db.sql(
		f"""
		SELECT pe.name AS pagamento, pe.posting_date, pe.mode_of_payment, pe.unallocated_amount
		FROM `tabPayment Entry` pe
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	linhas = []
	for r in rows:
		linhas.append(
			{
				"data": getdate(r.posting_date),
				"pagamento": r.pagamento,
				"modo_pagamento": r.mode_of_payment or "",
				"factura": None,
				"descricao": ADIANTAMENTO,
				"valor_factura": 0,
				"valor_alocado": flt(r.unallocated_amount),
				"saldo_factura": 0,
				"estado": "",
			}
		)
	return linhas
