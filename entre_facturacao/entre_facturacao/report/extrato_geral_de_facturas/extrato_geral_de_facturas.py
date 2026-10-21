"""Extrato Geral de Facturas: todas as facturas de todos os clientes num só
relatório - uma linha por factura com o cliente, valor líquido, IVA, total,
valor já pago, saldo pendente e estado. O filtro de cliente é opcional.
Os rascunhos só aparecem quando o estado "Rascunho" é pedido, e nunca entram
nos totais de facturado/pago/em aberto."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

from entre_facturacao.entre_facturacao.doctype.agenda_de_factura.agenda_de_factura import (
	invoice_naming_series,
)

RASCUNHO = "Rascunho"


def execute(filters=None):
	filters = filters or {}
	columns = get_columns()
	data = get_data(filters)
	report_summary = get_report_summary(data)
	if data:
		data.append(get_total_row(data))
	return columns, data, None, None, report_summary


def get_columns():
	return [
		{"label": _("Data"), "fieldname": "data", "fieldtype": "Date", "width": 95},
		{"label": _("Vencimento"), "fieldname": "vencimento", "fieldtype": "Date", "width": 95},
		{
			"label": _("Factura"),
			"fieldname": "factura",
			"fieldtype": "Link",
			"options": "Sales Invoice",
			"width": 120,
		},
		{
			"label": _("Cliente"),
			"fieldname": "cliente",
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{"label": _("Descrição"), "fieldname": "descricao", "fieldtype": "Data", "width": 200},
		{"label": _("Valor Líquido"), "fieldname": "valor_liquido", "fieldtype": "Currency", "width": 120},
		{"label": _("IVA"), "fieldname": "iva", "fieldtype": "Currency", "width": 100},
		{"label": _("Valor da Factura"), "fieldname": "valor_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Valor Pago"), "fieldname": "valor_pago", "fieldtype": "Currency", "width": 120},
		{"label": _("Saldo"), "fieldname": "saldo_factura", "fieldtype": "Currency", "width": 120},
		{"label": _("Estado"), "fieldname": "estado", "fieldtype": "Data", "width": 110},
	]


def parse_lista(valor):
	if not valor:
		return []
	if isinstance(valor, str):
		return frappe.parse_json(valor) if valor.startswith("[") else [valor]
	return valor


def get_data(filters):
	estados = parse_lista(filters.get("estado"))
	linhas = get_facturas(filters, incluir_rascunhos=RASCUNHO in estados)

	if estados:
		linhas = [l for l in linhas if l["estado"] in estados]

	return linhas


def get_facturas(filters, incluir_rascunhos=False):
	docstatus = "si.docstatus IN (0, 1)" if incluir_rascunhos else "si.docstatus = 1"
	conditions = [docstatus, "si.is_return = 0"]
	params = {}
	series = parse_lista(filters.get("serie"))
	if series:
		conditions.append("si.naming_series IN %(series)s")
		params["series"] = tuple(series)
	if filters.get("empresa"):
		conditions.append("si.company = %(empresa)s")
		params["empresa"] = filters["empresa"]
	if filters.get("cliente"):
		conditions.append("si.customer = %(cliente)s")
		params["cliente"] = filters["cliente"]
	if filters.get("data_inicio"):
		conditions.append("si.posting_date >= %(data_inicio)s")
		params["data_inicio"] = filters["data_inicio"]
	if filters.get("data_fim"):
		conditions.append("si.posting_date <= %(data_fim)s")
		params["data_fim"] = filters["data_fim"]

	rows = frappe.db.sql(
		f"""
		SELECT si.name, si.docstatus, si.posting_date, si.due_date, si.customer,
			si.net_total, si.total_taxes_and_charges, si.grand_total, si.outstanding_amount,
			si.invoice_title,
			COALESCE(SUM(CASE WHEN pe.name IS NOT NULL THEN per.allocated_amount END), 0) AS valor_pago
		FROM `tabSales Invoice` si
		LEFT JOIN `tabPayment Entry Reference` per
			ON per.reference_doctype = 'Sales Invoice' AND per.reference_name = si.name
		LEFT JOIN `tabPayment Entry` pe ON pe.name = per.parent AND pe.docstatus = 1
		WHERE {" AND ".join(conditions)}
		GROUP BY si.name
		ORDER BY si.posting_date DESC, si.name DESC
		""",
		params,
		as_dict=True,
	)

	today_date = getdate()
	linhas = []
	for r in rows:
		if r.docstatus == 0:
			estado = RASCUNHO
		elif flt(r.outstanding_amount) <= 0:
			estado = _("Paga")
		elif r.due_date and getdate(r.due_date) < today_date:
			estado = _("Vencida")
		else:
			estado = _("A Vencer")

		linhas.append(
			{
				"data": getdate(r.posting_date),
				"factura": r.name,
				"cliente": r.customer,
				"descricao": r.invoice_title or _("Factura Nº {0}").format(r.name),
				"vencimento": getdate(r.due_date) if r.due_date else None,
				"valor_liquido": flt(r.net_total),
				"iva": flt(r.total_taxes_and_charges),
				"valor_factura": flt(r.grand_total),
				"valor_pago": flt(r.valor_pago),
				"saldo_factura": flt(r.outstanding_amount),
				"estado": estado,
			}
		)
	return linhas


def get_total_row(linhas):
	"""Total row built here rather than via the Report's Add Total Row, so it
	does not depend on that setting being synced to the site."""
	emitidas = [l for l in linhas if l["estado"] != RASCUNHO]
	total = {"descricao": _("Total (sem rascunhos)"), "is_total_row": 1}
	for campo in ("valor_liquido", "iva", "valor_factura", "valor_pago", "saldo_factura"):
		total[campo] = flt(sum(l[campo] for l in emitidas))
	return total


def get_report_summary(todas):
	if not todas:
		return []

	rascunhos = [l for l in todas if l["estado"] == RASCUNHO]
	linhas = [l for l in todas if l["estado"] != RASCUNHO]

	total_facturado = flt(sum(l["valor_factura"] for l in linhas))
	total_pago = flt(sum(l["valor_pago"] for l in linhas))
	em_aberto = flt(sum(l["saldo_factura"] for l in linhas))
	vencido = flt(sum(l["saldo_factura"] for l in linhas if l["estado"] == _("Vencida")))
	num_clientes = len({l["cliente"] for l in todas})

	summary = [
		{"value": len(linhas), "label": _("Facturas"), "datatype": "Int"},
		{"value": num_clientes, "label": _("Clientes"), "datatype": "Int"},
		{"value": total_facturado, "label": _("Total Facturado"), "datatype": "Currency"},
		{"value": total_pago, "label": _("Total Pago"), "datatype": "Currency", "indicator": "Green"},
		{"value": em_aberto, "label": _("Em Aberto"), "datatype": "Currency", "indicator": "Orange"},
		{"value": vencido, "label": _("Vencido"), "datatype": "Currency", "indicator": "Red"},
	]
	if rascunhos:
		summary.append(
			{
				"value": flt(sum(l["valor_factura"] for l in rascunhos)),
				"label": _("Rascunhos ({0})").format(len(rascunhos)),
				"datatype": "Currency",
				"indicator": "Grey",
			}
		)
	return summary


@frappe.whitelist()
def get_series():
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return invoice_naming_series()
