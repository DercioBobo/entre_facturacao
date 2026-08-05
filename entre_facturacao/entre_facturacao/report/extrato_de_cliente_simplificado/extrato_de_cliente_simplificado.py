"""Extrato de Cliente Simplificado: uma linha por factura do cliente, com o
valor total já pago (somando todas as alocações de pagamento recebidas para
essa factura), o saldo pendente e o estado."""

import frappe
from frappe import _
from frappe.utils import flt, getdate


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
			"label": _("Factura"),
			"fieldname": "factura",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 120,
		},
		{"label": _("Descrição"), "fieldname": "descricao", "fieldtype": "Data", "width": 220},
		{"label": _("Valor da Factura"), "fieldname": "valor_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Valor Pago"), "fieldname": "valor_pago", "fieldtype": "Currency", "width": 120},
		{"label": _("Saldo"), "fieldname": "saldo_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Estado"), "fieldname": "estado", "fieldtype": "Data", "width": 110},
	]


def get_data(filters):
	cliente = filters["cliente"]
	empresa = filters.get("empresa")

	linhas = get_facturas(cliente, empresa)
	linhas.sort(key=lambda l: l["data"])

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
			linhas = [l for l in linhas if l["estado"] in estados]

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
		SELECT si.name, si.posting_date, si.due_date, si.grand_total, si.outstanding_amount,
			si.invoice_title, COALESCE(SUM(per.allocated_amount), 0) AS valor_pago
		FROM `tabSales Invoice` si
		LEFT JOIN `tabPayment Entry Reference` per
			ON per.reference_doctype = 'Sales Invoice' AND per.reference_name = si.name
		LEFT JOIN `tabPayment Entry` pe ON pe.name = per.parent AND pe.docstatus = 1
		WHERE {" AND ".join(conditions)}
		GROUP BY si.name
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
				"factura": r.name,
				"descricao": r.invoice_title or _("Factura Nº {0}").format(r.name),
				"valor_factura": flt(r.grand_total),
				"valor_pago": flt(r.valor_pago),
				"saldo_factura": flt(r.outstanding_amount),
				"estado": estado,
			}
		)
	return linhas
