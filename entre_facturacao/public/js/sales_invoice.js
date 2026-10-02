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

frappe.provide("entre_facturacao.invoice_repeat");

entre_facturacao.invoice_repeat = {
	MONTHS: { Monthly: 1, Quarterly: 3, "Half-yearly": 6, Yearly: 12 },

	// First cycle after the invoice's date that isn't in the past.
	default_start(frm, frequency) {
		const months = this.MONTHS[frequency] || 1;
		const today = frappe.datetime.get_today();
		let date = frm.doc.posting_date || today;
		do {
			date = frappe.datetime.add_months(date, months);
		} while (date < today);
		return date;
	},

	// Create an Auto Repeat that uses this invoice as its template.
	open(frm) {
		const d = new frappe.ui.Dialog({
			title: __("Criar Repetição Automática"),
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
					reqd: 1,
					onchange: () => d.set_value("start_date", this.default_start(frm, d.get_value("frequency"))),
				},
				{
					fieldname: "start_date",
					fieldtype: "Date",
					label: __("Primeira factura em"),
					default: this.default_start(frm, "Monthly"),
					reqd: 1,
				},
				{ fieldname: "end_date", fieldtype: "Date", label: __("Data de fim") },
				{ fieldtype: "Column Break" },
				{
					fieldname: "billing_mode",
					fieldtype: "Select",
					label: __("Modo de Facturação"),
					options: ["", "Antecipado", "Vencido"],
					default: "Antecipado",
					description: __(
						"Antecipado: factura o período corrente. Vencido: factura o período anterior. Vazio: título e descrições copiados sem alterações."
					),
				},
				{
					fieldname: "payment_days",
					fieldtype: "Int",
					label: __("Prazo de Pagamento (dias)"),
					description: __("Vazio: usa o mesmo prazo desta factura."),
				},
				{ fieldtype: "Section Break" },
				{ fieldname: "submit_on_creation", fieldtype: "Check", label: __("Submeter automaticamente") },
				{ fieldname: "notify_by_email", fieldtype: "Check", label: __("Enviar por email") },
				{
					fieldname: "recipients",
					fieldtype: "Small Text",
					label: __("Destinatários"),
					default: frm.doc.contact_email || "",
					depends_on: "notify_by_email",
					mandatory_depends_on: "notify_by_email",
				},
			],
			primary_action_label: __("Criar"),
			primary_action: (values) => {
				frappe.call({
					method: "entre_facturacao.auto_repeat.create_auto_repeat_from_invoice",
					args: { sales_invoice: frm.doc.name, ...values },
					freeze: true,
					callback: (r) => {
						if (!r.message) return;
						d.hide();
						frappe.show_alert({
							message: __("Repetição automática criada. Primeira factura: {0}. Verifique os modelos e a pré-visualização.", [
								frappe.datetime.str_to_user(r.message.next_schedule_date),
							]),
							indicator: "green",
						});
						frappe.set_route("Form", "Auto Repeat", r.message.name);
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

		if (frm.doc.docstatus === 1 && !frm.doc.is_return) {
			if (frm.doc.auto_repeat) {
				frm.add_custom_button(__("Repetição Automática"), () =>
					frappe.set_route("Form", "Auto Repeat", frm.doc.auto_repeat)
				);
			} else {
				frm.add_custom_button(__("Repetição Automática"), () => entre_facturacao.invoice_repeat.open(frm), __("Criar"));
			}
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
