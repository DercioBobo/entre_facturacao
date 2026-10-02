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

// Move an Auto Repeat's next invoice to another date, for this invoice only
// or (shift_following) for the rest of the schedule too.
entre_facturacao.auto_repeat.change_next_date = function (auto_repeat, { on_done } = {}) {
	const esc = frappe.utils.escape_html;
	const fmt = (d) => (d ? frappe.datetime.str_to_user(d) : "—");
	const get_info = (next_schedule_date) =>
		frappe.call({
			method: "entre_facturacao.auto_repeat.get_next_schedule_date_info",
			args: { auto_repeat, next_schedule_date },
		});

	get_info().then((r) => {
		const info = r.message;
		if (!info) return;

		const current = info.current_periodo
			? __("Actual: <b>{0}</b> (período {1}).", [fmt(info.current_date), esc(info.current_periodo)])
			: __("Actual: <b>{0}</b>.", [fmt(info.current_date)]);

		const d = new frappe.ui.Dialog({
			title: __("Alterar Próxima Data"),
			fields: [
				{ fieldname: "current_html", fieldtype: "HTML", options: `<p>${current}</p>` },
				{
					fieldname: "next_schedule_date",
					fieldtype: "Date",
					label: __("Nova próxima data"),
					default: info.current_date,
					reqd: 1,
					onchange: () => update_period(),
				},
				{ fieldname: "period_html", fieldtype: "HTML" },
				{
					fieldname: "shift_following",
					fieldtype: "Check",
					label: __("Mudar também as datas seguintes"),
					hidden: !info.month_based,
					description: __(
						"Desmarcado: só esta factura muda; as seguintes continuam no dia original. Marcado: as seguintes passam a seguir a nova data."
					),
				},
			],
			primary_action_label: __("Guardar"),
			primary_action: (values) => {
				frappe.call({
					method: "entre_facturacao.auto_repeat.set_next_schedule_date",
					args: { auto_repeat, ...values },
					freeze: true,
					callback: (res) => {
						const out = res.message;
						if (!out) return;
						d.hide();
						let message = __("Próxima factura: {0}.", [fmt(out.next_schedule_date)]);
						if (out.following_date) {
							message += " " + __("A seguinte: {0}.", [fmt(out.following_date)]);
						}
						frappe.show_alert({ message, indicator: "green" }, 8);
						on_done && on_done(out);
					},
				});
			},
		});

		const update_period = () => {
			const date = d.get_value("next_schedule_date");
			const $p = d.fields_dict.period_html.$wrapper;
			if (!date || !info.current_periodo) return $p.empty();
			get_info(date).then((res) => {
				const p = res.message && res.message.periodo;
				if (!p) return $p.empty();
				const changed = p !== info.current_periodo;
				$p.html(
					`<p class="${changed ? "text-warning" : "text-muted"}">${
						changed
							? __("Atenção: com esta data a factura passa a ser do período <b>{0}</b> (era {1}).", [
									esc(p),
									esc(info.current_periodo),
							  ])
							: __("Período facturado: <b>{0}</b>.", [esc(p)])
					}</p>`
				);
			});
		};

		d.show();
		update_period();
	});
};
