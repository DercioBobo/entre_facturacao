function balanco_set_nuit() {
	const empresa = frappe.query_report.get_filter_value("empresa");
	if (!empresa) return;
	frappe.db.get_value("Company", empresa, "tax_id").then(({ message }) => {
		frappe.query_report.set_filter_value("nuit", (message && message.tax_id) || "");
	});
}

frappe.query_reports["Balanco"] = {
	filters: [
		{
			fieldname: "empresa",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_default("company"),
			on_change: balanco_set_nuit,
		},
		{
			fieldname: "ano_fiscal",
			label: __("Ano Fiscal"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today()),
			on_change: () => {
				const ano_fiscal = frappe.query_report.get_filter_value("ano_fiscal");
				if (!ano_fiscal) return;
				frappe.db.get_value("Fiscal Year", ano_fiscal, "year_end_date").then(({ message }) => {
					frappe.query_report.set_filter_value("data_fim", message.year_end_date);
				});
			},
		},
		{
			fieldname: "data_fim",
			label: __("Data do Balanço"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "comparativo",
			label: __("Mostrar Período n-1"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "finance_book",
			label: __("Livro Contabilístico"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "nuit",
			label: __("NUIT"),
			fieldtype: "Data",
			hidden: 1,
		},
	],

	tree: true,
	name_field: "linha",
	parent_field: "parent_linha",
	initial_depth: 0,

	onload: () => balanco_set_nuit(),

	abrir_razao: (el) => {
		const qr = frappe.query_report;
		frappe.route_options = {
			company: qr.get_filter_value("empresa"),
			account: [el.dataset.account],
			to_date: qr.get_filter_value("data_fim"),
		};
		frappe.set_route("query-report", "General Ledger");
	},

	formatter: (value, row, column, data, default_formatter) => {
		if (data && data.is_cabecalho && column.fieldname !== "designacao") return "";
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "designacao" && data.account) {
			const account = frappe.utils.escape_html(data.account);
			value = `<a href="#" data-account="${account}"
				onclick="frappe.query_reports['Balanco'].abrir_razao(this); return false;">${value}</a>`;
		}
		if (data.is_aviso) {
			value = `<span style="color: var(--red-600, #c0392b);">${value}</span>`;
		}
		if (data.is_total || data.is_cabecalho) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
