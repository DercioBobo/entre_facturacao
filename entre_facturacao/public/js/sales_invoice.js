frappe.ui.form.on("Sales Invoice", {
	on_submit(frm) {
		if (frm.doc.auto_repeat) return;

		frappe.call({
			method: "entre_facturacao.auto_repeat.get_conflicting_auto_repeat",
			args: { sales_invoice: frm.doc.name },
			callback: (r) => {
				const conflict = r.message;
				if (!conflict) return;

				frappe.confirm(
					__(
						"Este cliente já tem uma factura automática agendada para {0} este mês. Deseja saltar esse agendamento e manter apenas esta factura?",
						[frappe.datetime.str_to_user(conflict.next_schedule_date)]
					),
					() => {
						frappe.call({
							method: "entre_facturacao.auto_repeat.skip_auto_repeat_this_month",
							args: { auto_repeat: conflict.name },
							callback: (res) => {
								if (res.message) {
									frappe.show_alert({
										message: __("Repetição automática saltada. Próxima factura: {0}", [
											frappe.datetime.str_to_user(res.message.next_schedule_date),
										]),
										indicator: "green",
									});
								}
							},
						});
					}
				);
			},
		});
	},
});
