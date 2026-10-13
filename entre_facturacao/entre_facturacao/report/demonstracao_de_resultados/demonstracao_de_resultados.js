function dr_set_nuit() {
	const empresa = frappe.query_report.get_filter_value("empresa");
	if (!empresa) return;
	frappe.db.get_value("Company", empresa, "tax_id").then(({ message }) => {
		frappe.query_report.set_filter_value("nuit", (message && message.tax_id) || "");
	});
}

// [nome, início, fim] do ano fiscal de hoje. O "year_start_date" dos defaults é o
// do ano fiscal por omissão em Global Defaults, que pode ainda ser o do ano anterior.
const DR_ANO_FISCAL_ACTUAL = erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true) || [];

frappe.query_reports["Demonstracao de Resultados"] = {
	filters: [
		{
			fieldname: "empresa",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_default("company"),
			on_change: dr_set_nuit,
		},
		{
			fieldname: "ano_fiscal",
			label: __("Ano Fiscal"),
			fieldtype: "Link",
			options: "Fiscal Year",
			reqd: 1,
			default: DR_ANO_FISCAL_ACTUAL[0],
			on_change: () => {
				const ano_fiscal = frappe.query_report.get_filter_value("ano_fiscal");
				if (!ano_fiscal) return;
				frappe.db.get_value("Fiscal Year", ano_fiscal, ["year_start_date", "year_end_date"]).then(({ message }) => {
					frappe.query_report.set_filter_value({
						data_inicio: message.year_start_date,
						data_fim: message.year_end_date,
					});
				});
			},
		},
		{
			fieldname: "data_inicio",
			label: __("De"),
			fieldtype: "Date",
			reqd: 1,
			default: DR_ANO_FISCAL_ACTUAL[1] || frappe.datetime.year_start(),
		},
		{
			fieldname: "data_fim",
			label: __("Até"),
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
			fieldname: "centro_de_custo",
			label: __("Centro de Custo"),
			fieldtype: "Link",
			options: "Cost Center",
			get_query: () => ({
				filters: { company: frappe.query_report.get_filter_value("empresa") },
			}),
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

	onload: () => dr_set_nuit(),

	abrir_razao: (el) => {
		const qr = frappe.query_report;
		frappe.route_options = {
			company: qr.get_filter_value("empresa"),
			account: [el.dataset.account],
			from_date: qr.get_filter_value("data_inicio"),
			to_date: qr.get_filter_value("data_fim"),
		};
		frappe.set_route("query-report", "General Ledger");
	},

	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "designacao" && data.account) {
			const account = frappe.utils.escape_html(data.account);
			value = `<a href="#" data-account="${account}"
				onclick="frappe.query_reports['Demonstracao de Resultados'].abrir_razao(this); return false;">${value}</a>`;
		}
		if (data.is_nao_mapeada) {
			value = `<span style="color: var(--red-600, #c0392b);">${value}</span>`;
		}
		if (data.is_subtotal) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
