"""Factura de Venda directamente a partir de uma Cotação.

ERPNext só factura a partir de Encomendas de Venda ou Guias de Remessa. Este
mapeamento segue o da Encomenda (erpnext.selling.doctype.quotation.quotation.
make_sales_order), mas com destino Sales Invoice.
"""

import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
from frappe.utils import cint, flt, getdate, nowdate

from entre_facturacao import features


@frappe.whitelist()
def make_sales_invoice(source_name, target_doc=None):
	"""Usado pelo botão Criar → Factura de Venda da Cotação e pelo
	Obter Itens de → Cotação da factura (frappe.model.mapper.map_docs)."""
	features.check("feature_factura_da_cotacao")
	_validate_quotation(source_name)
	customer = _get_customer(source_name)

	def set_missing_values(source, target):
		if customer:
			target.customer = customer.name
			target.customer_name = customer.customer_name
		if not target.get("quotation"):
			target.quotation = source.name
		if source.get("referral_sales_partner"):
			target.sales_partner = source.referral_sales_partner
			target.commission_rate = frappe.get_value(
				"Sales Partner", source.referral_sales_partner, "commission_rate"
			)
		target.ignore_pricing_rule = 1
		target.run_method("set_missing_values")
		target.run_method("calculate_taxes_and_totals")

	def update_item(source, target, source_parent):
		target.stock_qty = flt(source.qty) * flt(source.conversion_factor or 1)

	return get_mapped_doc(
		"Quotation",
		source_name,
		{
			"Quotation": {
				"doctype": "Sales Invoice",
				"validation": {"docstatus": ["=", 1]},
			},
			"Quotation Item": {
				"doctype": "Sales Invoice Item",
				"postprocess": update_item,
				# Itens alternativos não escolhidos ficam de fora.
				"condition": lambda d: not cint(d.get("is_alternative")),
			},
			"Sales Taxes and Charges": {
				"doctype": "Sales Taxes and Charges",
				"reset_value": True,
			},
			"Sales Team": {
				"doctype": "Sales Team",
				"add_if_empty": True,
			},
			# Payment Schedule não é copiado: as datas da cotação podem já ter
			# passado. A factura recalcula-o a partir do Payment Terms Template.
		},
		target_doc,
		set_missing_values,
	)


def _validate_quotation(name):
	q = frappe.db.get_value("Quotation", name, ["status", "valid_till", "docstatus"], as_dict=True)
	if not q:
		frappe.throw(_("Cotação {0} não existe.").format(name))
	if q.status == "Lost":
		frappe.throw(_("A cotação {0} está marcada como perdida.").format(name))
	if q.status == "Ordered":
		frappe.throw(
			_("A cotação {0} já tem Encomenda de Venda: facture a partir da encomenda.").format(name)
		)
	if (
		q.valid_till
		and getdate(q.valid_till) < getdate(nowdate())
		and not cint(
			frappe.db.get_single_value("Selling Settings", "allow_sales_order_creation_for_expired_quotation")
		)
	):
		frappe.throw(_("A validade da cotação {0} terminou.").format(name))


def _get_customer(quotation):
	"""Cliente da cotação. Cotações a Leads / Prospects convertem-se em
	Cliente como na criação da Encomenda de Venda."""
	try:
		from erpnext.selling.doctype.quotation.quotation import _make_customer
	except ImportError:
		_make_customer = None

	if _make_customer:
		return _make_customer(quotation)

	party = frappe.db.get_value("Quotation", quotation, ["quotation_to", "party_name"], as_dict=True)
	if party.quotation_to != "Customer":
		frappe.throw(_("Converta primeiro o {0} em Cliente.").format(_(party.quotation_to)))
	return frappe.get_doc("Customer", party.party_name)


def get_dashboard_data(data):
	"""override_doctype_dashboards: as facturas aparecem nas Ligações da Cotação."""
	data.setdefault("non_standard_fieldnames", {})["Sales Invoice"] = "quotation"
	for group in data.get("transactions", []):
		if "Sales Invoice" in group.get("items", []):
			return data
	data.setdefault("transactions", []).append({"label": _("Facturas"), "items": ["Sales Invoice"]})
	return data
