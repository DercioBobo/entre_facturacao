frappe.provide("entre_facturacao.quick_payment");

/**
 * Open the quick payment entry popup for a submitted Sales Invoice.
 * Used from the Monitor de Facturas page and from the Sales Invoice form.
 *
 * @param {string} invoice - Sales Invoice name.
 * @param {object} [opts]
 * @param {function} [opts.on_done] - called (with the new Payment Entry name)
 *        after the popup is closed, whether or not a payment was created.
 */
entre_facturacao.quick_payment.open = function (invoice, opts) {
	opts = opts || {};
	frappe.call({
		method: "entre_facturacao.quick_payment.get_quick_payment_defaults",
		args: { sales_invoice: invoice },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			entre_facturacao.quick_payment._show_dialog(invoice, r.message, opts);
		},
	});
};

entre_facturacao.quick_payment._show_dialog = function (invoice, defaults, opts) {
	const dialog = new frappe.ui.Dialog({
		title: __("Registar Pagamento — {0}", [invoice]),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info",
				options: `<div class="text-muted" style="margin-bottom: 10px;">
					${__("Cliente")}: <strong>${frappe.utils.escape_html(defaults.customer_name || defaults.customer)}</strong>
					&nbsp;·&nbsp;
					${__("Em dívida")}: <strong>${format_currency(defaults.outstanding_amount, defaults.currency)}</strong>
				</div>`,
			},
			{
				fieldtype: "Link",
				fieldname: "mode_of_payment",
				label: __("Modo de Pagamento"),
				options: "Mode of Payment",
				reqd: 1,
				default: defaults.mode_of_payment || "",
			},
			{
				fieldtype: "Currency",
				fieldname: "paid_amount",
				label: __("Valor Pago"),
				options: defaults.currency,
				reqd: 1,
				default: defaults.outstanding_amount,
			},
			{ fieldtype: "Column Break" },
			{
				fieldtype: "Date",
				fieldname: "posting_date",
				label: __("Data do Pagamento"),
				reqd: 1,
				default: defaults.posting_date,
			},
			{
				fieldtype: "Data",
				fieldname: "reference_no",
				label: __("Nº de Referência"),
			},
			{
				fieldtype: "Date",
				fieldname: "reference_date",
				label: __("Data de Referência"),
				default: defaults.posting_date,
			},
			{ fieldtype: "Section Break" },
			{
				fieldtype: "Small Text",
				fieldname: "remarks",
				label: __("Observações"),
			},
		],
		primary_action_label: __("Registar Pagamento"),
		primary_action: (values) => {
			dialog.get_primary_btn().prop("disabled", true);
			frappe.call({
				method: "entre_facturacao.quick_payment.create_quick_payment_entry",
				args: {
					sales_invoice: invoice,
					mode_of_payment: values.mode_of_payment,
					paid_amount: values.paid_amount,
					reference_no: values.reference_no,
					reference_date: values.reference_date,
					posting_date: values.posting_date,
					remarks: values.remarks,
				},
				freeze: true,
				freeze_message: __("A registar pagamento…"),
				callback: (r) => {
					if (!r.message) return;
					dialog.hide();
					entre_facturacao.quick_payment._after_submit(r.message.name, opts);
				},
				error: () => dialog.get_primary_btn().prop("disabled", false),
			});
		},
	});
	dialog.show();
};

entre_facturacao.quick_payment._after_submit = function (payment_entry, opts) {
	frappe.show_alert({
		message: __("Pagamento {0} registado com sucesso.", [payment_entry]),
		indicator: "green",
	});

	const done = () => opts.on_done && opts.on_done(payment_entry);

	const print_dialog = new frappe.ui.Dialog({
		title: __("Pagamento Registado"),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "msg",
				options: `<p>${__("O pagamento {0} foi registado e submetido com sucesso.", [
					`<a href="/app/payment-entry/${encodeURIComponent(payment_entry)}" target="_blank">${frappe.utils.escape_html(payment_entry)}</a>`,
				])}</p><p>${__("Deseja imprimir o recibo agora?")}</p>`,
			},
		],
		primary_action_label: __("Imprimir"),
		primary_action: () => {
			window.open(
				`/printview?doctype=${encodeURIComponent("Payment Entry")}&name=${encodeURIComponent(payment_entry)}`,
				"_blank"
			);
			print_dialog.hide();
		},
		secondary_action_label: __("Fechar"),
		secondary_action: () => print_dialog.hide(),
	});
	print_dialog.$wrapper.on("hidden.bs.modal", done);
	print_dialog.show();
};
