"""Custom fields that link to this app's own doctypes.

These can't live in fixtures/custom_field.json: a Link custom field is
validated against its target doctype, and on a site where that doctype
hasn't been created yet the fixture import fails with "Field ... is referring
to non-existing doctype". Here they are created after install / migrate, once
the app's doctypes exist.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields as _create

CUSTOM_FIELDS = {
	"Sales Invoice": [
		{
			"fieldname": "agenda_de_factura",
			"fieldtype": "Link",
			"label": "Agenda de Factura",
			"options": "Agenda de Factura",
			"insert_after": "billing_period_end",
			"read_only": 1,
			"no_copy": 1,
			"depends_on": "eval:doc.agenda_de_factura",
		},
	],
	# Classificação para o Apuramento de IVA (Modelo A); ver entre_facturacao/iva_modelo_a.py.
	"Account": [
		{
			"fieldname": "iva_modelo_a",
			"fieldtype": "Select",
			"label": "IVA (Modelo A)",
			"options": "\nIVA Liquidado\nIVA Dedutível\nIVA Dedutível - Importações\nIVA Regularizações",
			"insert_after": "account_type",
			"depends_on": "eval:!doc.is_group",
			"description": "Como os movimentos desta conta entram no Apuramento de IVA (Modelo A).",
		},
	],
	"Item Tax Template": [
		{
			"fieldname": "iva_campo_modelo_a",
			"fieldtype": "Select",
			"label": "Campo do Modelo A",
			"options": "\n01 - Tributada\n03 - Isenta com direito a dedução\n04 - Isenta sem direito a dedução",
			"insert_after": "company",
			"description": "Campo da Declaração Periódica de IVA para a base das vendas de artigos com este modelo.",
		},
	],
	"Sales Taxes and Charges Template": [
		{
			"fieldname": "iva_campo_modelo_a",
			"fieldtype": "Select",
			"label": "Campo do Modelo A (vendas sem IVA)",
			"options": "\n03 - Isenta com direito a dedução\n04 - Isenta sem direito a dedução",
			"insert_after": "tax_category",
			"description": "Campo da Declaração Periódica de IVA para as linhas sem IVA das facturas com este modelo (ex.: exportações = 03).",
		},
	],
}


def create_custom_fields():
	targets = {f["options"] for fields in CUSTOM_FIELDS.values() for f in fields if f["fieldtype"] == "Link"}
	missing = [dt for dt in targets if not frappe.db.exists("DocType", dt)]
	if missing:
		print(f"entre_facturacao: skipping custom fields, doctypes missing: {', '.join(missing)}")
		return
	_create(CUSTOM_FIELDS, update=True)
