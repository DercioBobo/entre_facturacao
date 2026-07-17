frappe.query_reports["Extrato da Factura"] = {
	filters: [
		{
			fieldname: "factura",
			label: __("Factura"),
			fieldtype: "Link",
			options: "Sales Invoice",
			reqd: 1,
		},
	],
};
