"""Extrato de Cliente Simplificado: lista todas as facturas de um cliente e,
para cada pagamento recebido, a que factura(s) foi alocado e em que valor -
dando visibilidade sobre a distribuição de pagamentos que cobrem várias
facturas ou que pagam apenas parte de uma factura."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

TIPO_FACTURA = 0
TIPO_ALOCACAO = 1
TIPO_ADIANTAMENTO = 2

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
		{"label": _("Tipo"), "fieldname": "tipo", "fieldtype": "Data", "width": 110},
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

	linhas = get_facturas(cliente, empresa) + get_alocacoes(cliente, empresa) + get_adiantamentos(cliente, empresa)
	linhas.sort(key=lambda l: (l["data"], l["_ordem"]))
	for l in linhas:
		del l["_ordem"]

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


def get_facturas(cliente, empresa=None):
	conditions = ["si.customer = %(cliente)s", "si.docstatus = 1", "si.is_return = 0"]
	params = {"cliente": cliente}
	if empresa:
		conditions.append("si.company = %(empresa)s")
		params["empresa"] = empresa

	rows = frappe.db.sql(
		f"""
		SELECT si.name, si.posting_date, si.due_date, si.grand_total, si.outstanding_amount, si.invoice_title
		FROM `tabSales Invoice` si
		WHERE {" AND ".join(conditions)}
		""",
		params,
		as_dict=True,
	)

	today_date = getdate()
	linhas = []
	for r in rows:
		estado = estado_factura(r.outstanding_amount, r.due_date, today_date)
		linhas.append(
			{
				"data": getdate(r.posting_date),
				"tipo": _("Factura"),
				"pagamento": None,
				"modo_pagamento": "",
				"factura": r.name,
				"descricao": r.invoice_title or _("Factura Nº {0}").format(r.name),
				"valor_factura": flt(r.grand_total),
				"valor_alocado": None,
				"saldo_factura": flt(r.outstanding_amount),
				"estado": estado,
				"_ordem": TIPO_FACTURA,
			}
		)
	return linhas


def estado_factura(outstanding_amount, due_date, today_date):
	if flt(outstanding_amount) <= 0:
		return _("Paga")
	if getdate(due_date) < today_date:
		return _("Vencida")
	return _("Em Dívida")


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
		estado = estado_factura(r.outstanding_amount, r.due_date, today_date)
		linhas.append(
			{
				"data": getdate(r.posting_date),
				"tipo": _("Alocação de Pagamento"),
				"pagamento": r.pagamento,
				"modo_pagamento": r.mode_of_payment or "",
				"factura": r.factura,
				"descricao": r.invoice_title or _("Factura Nº {0}").format(r.factura),
				"valor_factura": flt(r.grand_total),
				"valor_alocado": flt(r.allocated_amount),
				"saldo_factura": flt(r.outstanding_amount),
				"estado": estado,
				"_ordem": TIPO_ALOCACAO,
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
				"tipo": _("Adiantamento"),
				"pagamento": r.pagamento,
				"modo_pagamento": r.mode_of_payment or "",
				"factura": None,
				"descricao": ADIANTAMENTO,
				"valor_factura": None,
				"valor_alocado": flt(r.unallocated_amount),
				"saldo_factura": None,
				"estado": "",
				"_ordem": TIPO_ADIANTAMENTO,
			}
		)
	return linhas
