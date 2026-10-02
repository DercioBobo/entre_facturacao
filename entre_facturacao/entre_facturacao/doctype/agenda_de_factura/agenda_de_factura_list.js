frappe.listview_settings["Agenda de Factura"] = {
	add_fields: ["status", "sales_invoice"],
	get_indicator(doc) {
		const colors = { Agendada: "blue", Emitida: "green", Erro: "red", Cancelada: "gray" };
		return [__(doc.status), colors[doc.status] || "gray", "status,=," + doc.status];
	},
};
