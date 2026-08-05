frappe.query_reports["Extrato de Cliente Simplificado"] = {
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
			label: __("Estado da Factura"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				const options = [
					{ value: "Paga", description: __("Paga") },
					{ value: "Em Dívida", description: __("Em Dívida") },
					{ value: "Vencida", description: __("Vencida") },
				];
				txt = (txt || "").toLowerCase();
				return options.filter((o) => o.value.toLowerCase().includes(txt));
			},
		},
	],

	formatter: (value, row, column, data, default_formatter) => {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		if (column.fieldname === "tipo") {
			value = `<span style="font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.03em;">${value}</span>`;
		}
		if (column.fieldname === "descricao" && !data.factura) {
			value = `<span style="font-style: italic; color: var(--text-muted, #8d99a6);">${value}</span>`;
		}
		if (column.fieldname === "estado" && data.estado === __("Vencida")) {
			value = `<span style="color: var(--red-600, #c0392b); font-weight: 600;">${value}</span>`;
		}
		if (column.fieldname === "estado" && data.estado === __("Paga")) {
			value = `<span style="color: var(--green-600, #1f7a4d);">${value}</span>`;
		}
		if (column.fieldname === "valor_alocado" && data.valor_alocado) {
			value = `<span style="color: var(--green-600, #1f7a4d); font-weight: 600;">${value}</span>`;
		}
		return value;
	},
};
