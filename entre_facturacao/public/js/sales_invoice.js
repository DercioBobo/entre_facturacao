frappe.provide("entre_facturacao.manual_period");

entre_facturacao.manual_period = {
	MESES: [
		"Janeiro",
		"Fevereiro",
		"Março",
		"Abril",
		"Maio",
		"Junho",
		"Julho",
		"Agosto",
		"Setembro",
		"Outubro",
		"Novembro",
		"Dezembro",
	],

	// Pick the billing period of a manually created invoice; the period
	// mentioned in the title and item descriptions is swapped for it.
	open(frm) {
		const current = frm.doc.billing_period_start || frm.doc.posting_date || frappe.datetime.get_today();
		const [year, month] = current.split("-").map(Number);

		const d = new frappe.ui.Dialog({
			title: __("Período de Facturação"),
			fields: [
				{
					fieldname: "frequency",
					fieldtype: "Select",
					label: __("Frequência"),
					options: [
						{ label: __("Mensal"), value: "Monthly" },
						{ label: __("Trimestral"), value: "Quarterly" },
						{ label: __("Semestral"), value: "Half-yearly" },
						{ label: __("Anual"), value: "Yearly" },
					],
					default: "Monthly",
				},
				{
					fieldname: "month",
					fieldtype: "Select",
					label: __("Mês (início)"),
					options: this.MESES.map((m, i) => ({ label: m, value: String(i + 1) })),
					default: String(month),
					depends_on: "eval:doc.frequency !== 'Yearly'",
				},
				{ fieldname: "year", fieldtype: "Int", label: __("Ano"), default: year, reqd: 1 },
			],
			primary_action_label: __("Aplicar"),
			primary_action: (values) => {
				frappe.call({
					method: "entre_facturacao.billing_period.get_manual_period",
					args: { doc: frm.doc, ...values },
					freeze: true,
					callback: (r) => {
						const res = r.message;
						if (!res) return;

						frm.set_value("billing_period_start", res.billing_period_start);
						frm.set_value("billing_period_end", res.billing_period_end);
						frm.set_value("invoice_title", res.invoice_title);
						res.descriptions.forEach(({ idx, description }) => {
							const row = (frm.doc.items || []).find((item) => item.idx === idx);
							if (row && row.description !== description) {
								frappe.model.set_value(row.doctype, row.name, "description", description);
							}
						});

						d.hide();
						frappe.show_alert({
							message: res.changed
								? __("Período definido: {0}. Título e descrições actualizados.", [res.periodo])
								: __(
										"Período definido: {0}. Nenhuma menção a outro período encontrada no título ou nas descrições.",
										[res.periodo]
								  ),
							indicator: res.changed ? "green" : "orange",
						});
					},
				});
			},
		});
		d.show();
	},
};

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && flt(frm.doc.outstanding_amount) > 0) {
			frm.add_custom_button(__("Pagamento Rápido"), () => {
				entre_facturacao.quick_payment.open(frm.doc.name, {
					on_done: () => frm.reload_doc(),
				});
			}).addClass("btn-primary");
		}

		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Período de Facturação"), () => entre_facturacao.manual_period.open(frm));
		}
	},

	on_submit(frm) {
		if (frm.doc.auto_repeat) return;

		frappe.call({
			method: "entre_facturacao.auto_repeat.get_conflicting_auto_repeat",
			args: { sales_invoice: frm.doc.name },
			callback: (r) => {
				const conflict = r.message;
				if (!conflict) return;

				const message = conflict.periodo
					? __(
							"Este cliente já tem uma factura automática agendada para {0} referente a {1}. Deseja saltar esse agendamento e manter apenas esta factura?",
							[frappe.datetime.str_to_user(conflict.next_schedule_date), conflict.periodo]
					  )
					: __(
							"Este cliente já tem uma factura automática agendada para {0} este mês. Deseja saltar esse agendamento e manter apenas esta factura?",
							[frappe.datetime.str_to_user(conflict.next_schedule_date)]
					  );

				frappe.confirm(
					message,
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
