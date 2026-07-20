const EXTRATO_MESES = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function extrato_apply_month() {
	const mes = frappe.query_report.get_filter_value("mes");
	const ano = frappe.query_report.get_filter_value("ano");
	if (!mes || !ano) return;
	const month_index = EXTRATO_MESES.indexOf(mes) + 1;
	const pad = (n) => String(n).padStart(2, "0");
	const first = `${ano}-${pad(month_index)}-01`;
	const last_day = new Date(ano, month_index, 0).getDate();
	const last = `${ano}-${pad(month_index)}-${pad(last_day)}`;
	frappe.query_report.set_filter_value({
		ano_fiscal: "",
		data_inicio: first,
		data_fim: last,
	});
}

frappe.query_reports["Extrato de Cliente"] = {
	filters: [
		{
			fieldname: "cliente",
			label: __("Cliente"),
			fieldtype: "Link",
			options: "Customer",
			reqd: 1,
		},
		{
			fieldname: "empresa",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "mes",
			label: __("Mês"),
			fieldtype: "Select",
			options: "\n" + EXTRATO_MESES.join("\n"),
			on_change: extrato_apply_month,
		},
		{
			fieldname: "ano",
			label: __("Ano"),
			fieldtype: "Int",
			default: new Date().getFullYear(),
			on_change: extrato_apply_month,
		},
		{
			fieldname: "ano_fiscal",
			label: __("Ano Fiscal"),
			fieldtype: "Link",
			options: "Fiscal Year",
			on_change: () => {
				const fiscal_year = frappe.query_report.get_filter_value("ano_fiscal");
				if (!fiscal_year) return;
				frappe.db.get_value("Fiscal Year", fiscal_year, ["year_start_date", "year_end_date"]).then(({ message }) => {
					frappe.query_report.set_filter_value({
						mes: "",
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
		},
		{
			fieldname: "data_fim",
			label: __("Até"),
			fieldtype: "Date",
		},
		{
			fieldname: "tipo",
			label: __("Tipo"),
			fieldtype: "Select",
			options: "Facturas e Pagamentos\nSó Facturas\nSó Pagamentos",
			default: "Facturas e Pagamentos",
		},
	],

	onload: () => {
		const empresa = frappe.query_report.get_filter_value("empresa");
		if (!empresa) return;
		frappe.call({
			method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_default_fiscal_year",
			args: { company: empresa },
		}).then((r) => {
			if (!r.message) return;
			frappe.query_report.set_filter_value({
				ano_fiscal: r.message.name,
				data_inicio: r.message.year_start_date,
				data_fim: r.message.year_end_date,
			});
		});
	},

	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		if (column.fieldname === "debito" && data.debito) {
			value = `<span style="color: var(--red-600, #c0392b);">${value}</span>`;
		}
		if (column.fieldname === "credito" && data.credito) {
			value = `<span style="color: var(--green-600, #1f7a4d); font-weight: 600;">${value}</span>`;
		}
		if (column.fieldname === "estado" && data.estado === __("Vencida")) {
			value = `<span style="color: var(--red-600, #c0392b); font-weight: 600;">${value}</span>`;
		}
		if (column.fieldname === "tipo") {
			value = `<span style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em;">${value}</span>`;
		}
		return value;
	},
};
