frappe.provide("entre_facturacao.quotation");

entre_facturacao.quotation = {
	// Avisa se a cotação já tem facturas antes de criar outra.
	make_invoice(frm) {
		const open = () =>
			frappe.model.open_mapped_doc({
				method: "entre_facturacao.quotation.make_sales_invoice",
				frm,
			});

		frappe.db
			.get_list("Sales Invoice", {
				filters: { quotation: frm.doc.name, docstatus: ["!=", 2] },
				fields: ["name"],
				limit: 5,
			})
			.then((invoices) => {
				if (!invoices.length) return open();
				const links = invoices
					.map((r) => `<a href="/app/sales-invoice/${encodeURIComponent(r.name)}">${frappe.utils.escape_html(r.name)}</a>`)
					.join(", ");
				frappe.confirm(
					__("Esta cotação já foi facturada em {0}. Criar outra factura?", [links]),
					open
				);
			});
	},
};

frappe.ui.form.on("Quotation", {
	refresh(frm) {
		if (!entre_facturacao.feature("feature_factura_da_cotacao")) return;
		if (frm.doc.docstatus !== 1 || ["Lost", "Ordered"].includes(frm.doc.status)) return;

		frm.add_custom_button(__("Factura de Venda"), () => entre_facturacao.quotation.make_invoice(frm), __("Create"));
	},
});
