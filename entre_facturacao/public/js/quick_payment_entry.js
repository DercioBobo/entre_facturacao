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

/**
 * Open the quick payment popup for several submitted Sales Invoices of the
 * SAME customer at once. Creates a single Payment Entry with one reference
 * row per invoice, allocated oldest-due-date first.
 *
 * @param {string[]} invoices - Sales Invoice names, all the same customer.
 * @param {object} [opts]
 * @param {function} [opts.on_done] - called (with the new Payment Entry name)
 *        after the popup is closed, whether or not a payment was created.
 */
entre_facturacao.quick_payment.open_bulk = function (invoices, opts) {
	opts = opts || {};
	if (!invoices || !invoices.length) return;
	frappe.call({
		method: "entre_facturacao.quick_payment.get_bulk_payment_defaults",
		args: { invoices },
		freeze: true,
		callback: (r) => {
			if (!r.message) return;
			entre_facturacao.quick_payment._show_bulk_dialog(invoices, r.message, opts);
		},
	});
};

entre_facturacao.quick_payment._show_bulk_dialog = function (invoices, defaults, opts) {
	const rows_html = defaults.invoices
		.map(
			(row) => `
			<tr>
				<td>${frappe.utils.escape_html(row.invoice)}</td>
				<td>${row.due_date ? frappe.datetime.str_to_user(row.due_date) : "—"}</td>
				<td style="text-align:right">${format_currency(row.outstanding_amount, defaults.currency)}</td>
			</tr>`
		)
		.join("");

	const dialog = new frappe.ui.Dialog({
		title: __("Registar Pagamento — {0} factura(s)", [defaults.count]),
		fields: [
			{
				fieldtype: "HTML",
				fieldname: "info",
				options: `<div class="text-muted" style="margin-bottom: 10px;">
					${__("Cliente")}: <strong>${frappe.utils.escape_html(defaults.customer_name || defaults.customer)}</strong>
					&nbsp;·&nbsp;
					${__("Total em dívida")}: <strong>${format_currency(defaults.total_outstanding, defaults.currency)}</strong>
				</div>
				<table class="table table-condensed" style="margin-bottom: 14px;">
					<thead><tr>
						<th>${__("Factura")}</th>
						<th>${__("Vencimento")}</th>
						<th style="text-align:right">${__("Em Dívida")}</th>
					</tr></thead>
					<tbody>${rows_html}</tbody>
				</table>`,
			},
			{
				fieldtype: "Link",
				fieldname: "mode_of_payment",
				label: __("Modo de Pagamento"),
				options: "Mode of Payment",
				reqd: 1,
			},
			{
				fieldtype: "Currency",
				fieldname: "paid_amount",
				label: __("Valor Pago"),
				options: defaults.currency,
				reqd: 1,
				default: defaults.total_outstanding,
				description: __("Se for inferior ao total, é aplicado às facturas mais antigas primeiro."),
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
				method: "entre_facturacao.quick_payment.create_bulk_payment_entry",
				args: {
					invoices,
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
