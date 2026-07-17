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
			fieldname: "data_inicio",
			label: __("De"),
			fieldtype: "Date",
		},
		{
			fieldname: "data_fim",
			label: __("Até"),
			fieldtype: "Date",
		},
	],

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
