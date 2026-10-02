frappe.provide("entre_facturacao.auto_repeat");

// Issue an Auto Repeat's next invoice today (customer pays ahead) and move
// its schedule on one cycle, as if it had run on its date.
entre_facturacao.auto_repeat.issue_now = function (auto_repeat, { on_done } = {}) {
	frappe.call({
		method: "entre_facturacao.auto_repeat.get_issue_now_info",
		args: { auto_repeat },
		callback: (r) => {
			const info = r.message;
			if (!info) return;
			const esc = frappe.utils.escape_html;
			const fmt = (d) => (d ? frappe.datetime.str_to_user(d) : "—");

			let message = __("Emitir hoje a factura prevista para <b>{0}</b>?", [fmt(info.schedule_date)]);
			if (info.periodo) {
				message += "<br>" + __("Período facturado: <b>{0}</b>.", [esc(info.periodo)]);
			}
			message +=
				"<br><br>" +
				__("A próxima emissão automática passa para <b>{0}</b>, como se esta tivesse sido emitida na data prevista.", [
					fmt(info.next_schedule_date),
				]);
			if (!info.submit_on_creation) {
				message += "<br>" + __("A factura fica em rascunho (a repetição não submete automaticamente).");
			}

			frappe.confirm(message, () =>
				frappe.call({
					method: "entre_facturacao.auto_repeat.issue_auto_repeat_now",
					args: { auto_repeat },
					freeze: true,
					freeze_message: __("A emitir a factura..."),
					callback: (res) => {
						const out = res.message;
						if (!out) return;
						frappe.show_alert(
							{
								message: __("Factura {0} emitida. Próxima emissão: {1}.", [
									`<a href="/app/sales-invoice/${encodeURIComponent(out.invoice)}">${esc(out.invoice)}</a>`,
									fmt(out.next_schedule_date),
								]),
								indicator: "green",
							},
							10
						);
						on_done && on_done(out);
					},
				})
			);
		},
	});
};
