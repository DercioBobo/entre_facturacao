"""Extrato de Cliente: ledger cronológico de tudo o que aconteceu com um
cliente - facturas emitidas (débito) e pagamentos recebidos (crédito) - com
um Saldo Devedor corrido, tal como um extrato de conta real."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

TIPO_FACTURA = 0
TIPO_PAGAMENTO = 1


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
		{"label": _("Tipo"), "fieldname": "tipo", "fieldtype": "Data", "width": 100},
		{
			"label": _("Documento"),
			"fieldname": "documento",
			"fieldtype": "Dynamic Link",
			"options": "documento_doctype",
			"width": 150,
		},
		{"label": _("Descrição"), "fieldname": "descricao", "fieldtype": "Data", "width": 220},
		{"label": _("Débito"), "fieldname": "debito", "fieldtype": "Currency", "width": 110},
		{"label": _("Crédito"), "fieldname": "credito", "fieldtype": "Currency", "width": 110},
		{"label": _("Estado"), "fieldname": "estado", "fieldtype": "Data", "width": 100},
		{"label": _("Saldo Devedor"), "fieldname": "saldo_devedor", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	cliente = filters["cliente"]
	empresa = filters.get("empresa")
	tipo = filters.get("tipo")

	eventos = []
	if tipo != "Só Pagamentos":
		eventos += get_eventos_factura(cliente, empresa)
	if tipo != "Só Facturas":
		eventos += get_eventos_pagamento(cliente, empresa)

	eventos.sort(key=lambda e: (e["data"], e["_ordem"]))

	saldo = 0
	for e in eventos:
		saldo = flt(saldo + e["debito"] - e["credito"])
		e["saldo_devedor"] = saldo
		del e["_ordem"]

	data_inicio = getdate(filters["data_inicio"]) if filters.get("data_inicio") else None
	data_fim = getdate(filters["data_fim"]) if filters.get("data_fim") else None
	if data_inicio:
		eventos = [e for e in eventos if e["data"] >= data_inicio]
	if data_fim:
		eventos = [e for e in eventos if e["data"] <= data_fim]

	eventos.sort(key=lambda e: e["data"], reverse=True)

	return eventos


def get_eventos_factura(cliente, empresa=None):
	conditions = ["si.customer = %(cliente)s", "si.docstatus = 1", "si.is_return = 0"]
	params = {"cliente": cliente}
	if empresa:
		conditions.append("si.company = %(empresa)s")
		params["empresa"] = empresa

	rows = frappe.db.sql(
		f"""
		SELECT si.name, si.posting_date, si.due_date, si.grand_total, si.outstanding_amount
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	today_date = getdate()
	eventos = []
	for r in rows:
		if flt(r.outstanding_amount) <= 0:
			estado = _("Paga")
		elif getdate(r.due_date) < today_date:
			estado = _("Vencida")
		else:
			estado = _("Em Dívida")

		eventos.append(
			{
				"data": getdate(r.posting_date),
				"tipo": _("Factura"),
				"documento": r.name,
				"documento_doctype": "Sales Invoice",
				"descricao": _("Factura Nº {0}").format(r.name),
				"debito": flt(r.grand_total),
				"credito": 0,
				"estado": estado,
				"_ordem": TIPO_FACTURA,
			}
		)
	return eventos


def get_eventos_pagamento(cliente, empresa=None):
	conditions = ["pe.party_type = 'Customer'", "pe.party = %(cliente)s", "pe.docstatus = 1"]
	params = {"cliente": cliente}
	if empresa:
		conditions.append("pe.company = %(empresa)s")
		params["empresa"] = empresa

	rows = frappe.db.sql(
		f"""
		SELECT pe.name, pe.posting_date, pe.paid_amount, pe.mode_of_payment
		FROM `tabPayment Entry` pe
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	eventos = []
	for r in rows:
		modo = r.mode_of_payment or ""
		descricao = _("Pagamento recebido ({0})").format(modo) if modo else _("Pagamento recebido")
		eventos.append(
			{
				"data": getdate(r.posting_date),
				"tipo": _("Pagamento"),
				"documento": r.name,
				"documento_doctype": "Payment Entry",
				"descricao": descricao,
				"debito": 0,
				"credito": flt(r.paid_amount),
				"estado": "",
				"_ordem": TIPO_PAGAMENTO,
			}
		)
	return eventos
