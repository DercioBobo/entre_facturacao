frappe.ui.form.on("Agenda de Factura", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		if (frm.is_new() && !frm.doc.scheduled_date) {
			frm.set_value("scheduled_date", frappe.datetime.add_days(frappe.datetime.get_today(), 1));
		}
	},

	setup(frm) {
		frm.set_query("taxes_and_charges", () => ({ filters: { company: frm.doc.company } }));
		set_naming_series_options(frm);
	},

	after_save(frm) {
		// Saved with today's date (or earlier): offer to issue right away
		// instead of waiting for the hourly job.
		if (frm._issuing || frm.doc.status !== "Agendada") return;
		if (frm.doc.scheduled_date > frappe.datetime.get_today()) return;
		frappe.confirm(
			__("A data de emissão já chegou. Emitir a factura agora? (Se não, será emitida automaticamente dentro de uma hora.)"),
			() => run_issue(frm)
		);
	},

	refresh(frm) {
		const status = frm.doc.status;

		if ((frm.doc.items || []).length) {
			frm.add_custom_button(__("Pré-visualizar Factura"), () => preview(frm));
		}

		if (status === "Emitida") {
			frm.disable_form();
			if (frm.doc.sales_invoice) {
				frm.add_custom_button(__("Ver Factura"), () =>
					frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice)
				);
				frm.dashboard.set_headline_alert(
					__("Factura {0} emitida em {1}.", [
						`<a href="/app/sales-invoice/${encodeURIComponent(frm.doc.sales_invoice)}">${frappe.utils.escape_html(frm.doc.sales_invoice)}</a>`,
						frappe.datetime.str_to_user(frm.doc.issued_on),
					]),
					"green"
				);
			}
			return;
		}

		if (status === "Cancelada") {
			frm.disable_form();
			frm.add_custom_button(__("Reactivar"), () =>
				frm.call("reactivate").then(() => frm.reload_doc())
			);
			return;
		}

		frm.add_custom_button(
			status === "Erro" ? __("Tentar Novamente") : __("Emitir Agora"),
			() => issue_now(frm)
		);
		if (frm.is_new()) return;

		frm.add_custom_button(__("Cancelar Agendamento"), () =>
			frappe.confirm(__("Cancelar esta agenda? A factura não será emitida."), () =>
				frm.call("cancel_schedule").then(() => frm.reload_doc())
			)
		);

		if (status === "Erro") {
			frm.dashboard.set_headline_alert(
				__("A emissão falhou: {0}. Corrija e guarde para voltar a agendar, ou clique em Tentar Novamente.", [
					frappe.utils.escape_html(frm.doc.error_message || ""),
				]),
				"red"
			);
		} else if (frm.doc.scheduled_date <= frappe.datetime.get_today()) {
			frm.dashboard.set_headline_alert(
				__("A data de emissão já chegou: a factura será emitida dentro de uma hora."),
				"orange"
			);
		}
	},

	billing_period_start(frm) {
		if (frm.doc.billing_period_start && !frm.doc.billing_period_end) {
			frm.set_value("billing_period_end", frappe.datetime.month_end(frm.doc.billing_period_start));
		}
	},
});

frappe.ui.form.on("Agenda de Factura Item", {
	qty: set_amount,
	rate: set_amount,
});

function set_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

function set_naming_series_options(frm) {
	frappe
		.call("entre_facturacao.entre_facturacao.doctype.agenda_de_factura.agenda_de_factura.get_invoice_naming_series")
		.then((r) => {
			const res = r.message || {};
			const options = res.options || [];
			frm.set_df_property("invoice_naming_series", "options", [""].concat(options));
			if (frm.is_new() && !frm.doc.invoice_naming_series) {
				const fallback = options.includes(res.default) ? res.default : options[0];
				if (fallback) frm.set_value("invoice_naming_series", fallback);
			}
			frm.refresh_field("invoice_naming_series");
		});
}

// Issue now, skipping the wait. An unsaved / changed agenda is saved first.
function issue_now(frm) {
	frappe.confirm(__("Emitir a factura agora, com a data de hoje?"), () => {
		if (!frm.is_new() && !frm.is_dirty()) {
			run_issue(frm);
			return;
		}
		frm._issuing = true;
		frm.save()
			.then(() => run_issue(frm))
			.finally(() => (frm._issuing = false));
	});
}

function run_issue(frm) {
	return frm
		.call({ method: "issue_now", freeze: true, freeze_message: __("A emitir a factura...") })
		.then((r) => {
			frm.reload_doc();
			if (r.message) {
				frappe.show_alert({ message: __("Factura {0} emitida.", [r.message]), indicator: "green" });
			}
		});
}

function preview(frm) {
	const d = new frappe.ui.Dialog({
		title: __("Pré-visualização da Factura"),
		size: "extra-large",
		fields: [
			{
				fieldname: "print_format",
				fieldtype: "Link",
				label: __("Formato de Impressão"),
				options: "Print Format",
				get_query: () => ({ filters: { doc_type: "Sales Invoice", disabled: 0 } }),
				change: () => render(),
			},
			{ fieldname: "col", fieldtype: "Column Break" },
			{ fieldname: "summary", fieldtype: "HTML" },
			{ fieldname: "sec", fieldtype: "Section Break" },
			{ fieldname: "preview", fieldtype: "HTML" },
		],
	});

	let last_format;
	const render = () => {
		const print_format = d.get_value("print_format") || null;
		if (last_format !== undefined && print_format === last_format) return;
		last_format = print_format;

		frappe.call({
			method: "entre_facturacao.entre_facturacao.doctype.agenda_de_factura.agenda_de_factura.get_preview",
			args: { doc: frm.doc, print_format },
			freeze: true,
			callback: (r) => {
				const res = r.message;
				if (!res) return;

				if (!print_format && res.print_format) {
					last_format = res.print_format;
					d.set_value("print_format", res.print_format);
				}

				const money = (v) => format_currency(v, res.currency);
				d.get_field("summary").$wrapper.html(`
					<div class="text-muted small" style="line-height: 1.8; padding-top: 4px;">
						${__("Nº previsto")}: <b>${frappe.utils.escape_html(res.invoice_name || "—")}</b>
						<span title="${__("O número final é atribuído no momento da emissão.")}">(${__("série")} ${frappe.utils.escape_html(res.naming_series || "—")})</span><br>
						${__("Emissão")}: <b>${frappe.datetime.str_to_user(res.posting_date)}</b> &nbsp;·&nbsp;
						${__("Vencimento")}: <b>${res.due_date ? frappe.datetime.str_to_user(res.due_date) : "—"}</b><br>
						${__("Líquido")}: ${money(res.net_total)} &nbsp;·&nbsp;
						${__("Impostos")}: ${money(res.total_taxes_and_charges)} &nbsp;·&nbsp;
						${__("Total")}: <b>${money(res.grand_total)}</b>
					</div>
				`);

				const css = frappe.assets.bundled_asset("print.bundle.css");
				const html = `<!doctype html><html><head>
					<meta charset="utf-8">
					<link rel="stylesheet" href="${frappe.urllib.get_base_url()}${css}">
					<style>${res.style || ""}</style>
					</head><body>
					<div class="print-format-gutter"><div class="print-format">${res.html || ""}</div></div>
					</body></html>`;

				const $frame = $(
					'<iframe style="width: 100%; height: 75vh; border: 1px solid var(--border-color); border-radius: var(--border-radius); background: #fff;"></iframe>'
				);
				d.get_field("preview").$wrapper.empty().append($frame);
				$frame[0].srcdoc = html;
			},
		});
	};

	d.show();
	render();
}
