function balancete_set_nuit() {
	const empresa = frappe.query_report.get_filter_value("empresa");
	if (!empresa) return;
	frappe.db.get_value("Company", empresa, "tax_id").then(({ message }) => {
		frappe.query_report.set_filter_value("nuit", (message && message.tax_id) || "");
	});
}

frappe.query_reports["Balancete"] = {
	filters: [
		{
			fieldname: "empresa",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_default("company"),
			on_change: balancete_set_nuit,
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
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "data_fim",
			label: __("Até"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
		{
			fieldname: "tipo",
			label: __("Tipo"),
			fieldtype: "Select",
			options: ["Analítico", "Sintético", "Movimento"].join("\n"),
			default: "Analítico",
			description: __("Analítico: todas as contas. Sintético: só contas agregadoras. Movimento: só contas de lançamento."),
		},
		{
			fieldname: "nivel",
			label: __("Nível (Grau)"),
			fieldtype: "Int",
			description: __("Profundidade máxima no plano de contas; vazio mostra todas."),
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
			fieldname: "excluir_apuramento",
			label: __("Antes do Apuramento de Resultados"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "mostrar_sem_movimento",
			label: __("Mostrar Contas sem Movimento"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "nuit",
			label: __("NUIT"),
			fieldtype: "Data",
			hidden: 1,
		},
	],

	tree: true,
	name_field: "account",
	parent_field: "parent_account",
	initial_depth: 3,

	onload: () => balancete_set_nuit(),

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

		if (column.fieldname === "designacao" && data.account && !data.is_group) {
			const account = frappe.utils.escape_html(data.account);
			value = `<a href="#" data-account="${account}"
				onclick="frappe.query_reports['Balancete'].abrir_razao(this); return false;">${value}</a>`;
		}
		if (data.is_total || data.is_group) {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
