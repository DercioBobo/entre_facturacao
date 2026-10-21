// Inside an IIFE: report scripts are evaluated in the global scope, and
// Extrato de Cliente already declares its own month helpers there.
(() => {
	const MESES = [
		"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
		"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
	];

	function apply_month() {
		const mes = frappe.query_report.get_filter_value("mes");
		if (!mes) return;
		const data_inicio_atual = frappe.query_report.get_filter_value("data_inicio");
		const ano = data_inicio_atual ? parseInt(data_inicio_atual.substring(0, 4), 10) : new Date().getFullYear();
		const month_index = MESES.indexOf(mes) + 1;
		const pad = (n) => String(n).padStart(2, "0");
		const last_day = new Date(ano, month_index, 0).getDate();
		frappe.query_report.set_filter_value({
			ano_fiscal: "",
			data_inicio: `${ano}-${pad(month_index)}-01`,
			data_fim: `${ano}-${pad(month_index)}-${pad(last_day)}`,
		});
	}

	frappe.query_reports["Extrato Geral de Facturas"] = {
		filters: [
			{
				fieldname: "empresa",
				label: __("Empresa"),
				fieldtype: "Link",
				options: "Company",
				default: frappe.defaults.get_default("company"),
			},
			{
				fieldname: "cliente",
				label: __("Cliente"),
				fieldtype: "Link",
				options: "Customer",
			},
			{
				fieldname: "serie",
				label: __("Série"),
				fieldtype: "MultiSelectList",
				get_data: function (txt) {
					return frappe
						.call("entre_facturacao.entre_facturacao.report.extrato_geral_de_facturas.extrato_geral_de_facturas.get_series")
						.then((r) => {
							txt = (txt || "").toLowerCase();
							return (r.message || [])
								.filter((s) => s.toLowerCase().includes(txt))
								.map((s) => ({ value: s, description: "" }));
						});
				},
			},
			{
				fieldname: "mes",
				label: __("Mês"),
				fieldtype: "Select",
				options: "\n" + MESES.join("\n"),
				on_change: apply_month,
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
				fieldname: "estado",
				label: __("Estado"),
				fieldtype: "MultiSelectList",
				get_data: function (txt) {
					const options = [
						{ value: "Paga", description: __("Paga") },
						{ value: "A Vencer", description: __("A Vencer") },
						{ value: "Vencida", description: __("Vencida") },
						{ value: "Rascunho", description: __("Rascunho") },
					];
					txt = (txt || "").toLowerCase();
					return options.filter((o) => o.value.toLowerCase().includes(txt));
				},
			},
		],

		onload: () => {
			const empresa = frappe.query_report.get_filter_value("empresa");
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

			if (data.is_total_row) {
				return value ? `<b>${value}</b>` : value;
			}

			if (column.fieldname === "estado" && data.estado === __("Vencida")) {
				value = `<span style="color: var(--red-600, #c0392b); font-weight: 600;">${value}</span>`;
			}
			if (column.fieldname === "estado" && data.estado === __("Paga")) {
				value = `<span style="color: var(--green-600, #1f7a4d);">${value}</span>`;
			}
			if (data.estado === "Rascunho") {
				return `<span style="color: var(--gray-500, #8d99a6); font-style: italic;">${value}</span>`;
			}
			if (column.fieldname === "valor_pago" && data.valor_pago) {
				value = `<span style="color: var(--green-600, #1f7a4d); font-weight: 600;">${value}</span>`;
			}
			if (column.fieldname === "saldo_factura" && data.saldo_factura > 0) {
				value = `<span style="color: var(--orange-600, #b8620a); font-weight: 600;">${value}</span>`;
			}
			return value;
		},
	};
})();
