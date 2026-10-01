frappe.provide("entre_facturacao.billing_period");

entre_facturacao.billing_period = {
	is_invoice(frm) {
		return frm.doc.reference_doctype === "Sales Invoice" && frm.doc.reference_document;
	},

	copy_from_template(frm) {
		if (!frm.doc.billing_mode) {
			frappe.msgprint(__("Escolha primeiro o Modo de Facturação (Antecipado ou Vencido)."));
			return;
		}

		const run = () =>
			frappe.call({
				method: "entre_facturacao.billing_period.get_template_suggestions",
				args: {
					reference_document: frm.doc.reference_document,
					frequency: frm.doc.frequency,
					billing_mode: frm.doc.billing_mode,
				},
				freeze: true,
				callback: (r) => {
					const s = r.message;
					if (!s) return;

					frm.set_value("title_template", s.title_template || "");
					frm.clear_table("billing_descriptions");
					s.rows.forEach((row) => frm.add_child("billing_descriptions", row));
					frm.refresh_field("billing_descriptions");
					frm.dirty();

					frappe.msgprint({
						title: __("Modelos criados"),
						indicator: "green",
						message: __(
							"A factura modelo foi tratada como sendo de <b>{0}</b>. As menções a esse período foram trocadas por variáveis como {1}. Verifique os modelos e a pré-visualização antes de guardar.",
							[frappe.utils.escape_html(s.periodo), "<code>{{ mes }}</code>"]
						),
					});
				},
			});

		if ((frm.doc.billing_descriptions || []).length || frm.doc.title_template) {
			frappe.confirm(
				__("Isto substitui o Modelo do Título e os Modelos das Descrições actuais. Continuar?"),
				run
			);
		} else {
			run();
		}
	},

	render_preview(frm) {
		const field = frm.get_field("billing_preview");
		if (!field) return;
		if (!this.is_invoice(frm) || !frm.doc.billing_mode) {
			field.$wrapper.empty();
			return;
		}

		clearTimeout(this._preview_timer);
		this._preview_timer = setTimeout(() => {
			frappe.call({
				method: "entre_facturacao.billing_period.preview_next_invoice",
				args: { doc: frm.doc },
				callback: (r) => field.$wrapper.html(this.preview_html(r.message)),
				error: () =>
					field.$wrapper.html(
						`<div class="text-muted">${__("Não foi possível gerar a pré-visualização. Verifique os modelos.")}</div>`
					),
			});
		}, 400);
	},

	preview_html(p) {
		if (!p) {
			return `<div class="text-muted">${__("Sem pré-visualização: verifique a frequência e a próxima data.")}</div>`;
		}
		const esc = frappe.utils.escape_html;
		if (p.error) {
			return `<div class="text-danger">${__("Erro no modelo")}: ${esc(p.error)}</div>`;
		}
		const items = p.items
			.map(
				(item) => `
				<div style="border-top: 1px solid var(--border-color); padding: 8px 0;">
					<div class="text-muted small">${__("Linha")} ${item.idx} · ${esc(item.item_code || "")}</div>
					<div>${item.description || ""}</div>
				</div>`
			)
			.join("");

		return `
			<div style="border: 1px solid var(--border-color); border-radius: var(--border-radius); padding: 12px;">
				<div class="text-muted small">
					${__("Próxima factura")}: <b>${frappe.datetime.str_to_user(p.posting_date)}</b>
					· ${__("Período")}: <b>${esc(p.periodo)}</b>
					(${frappe.datetime.str_to_user(p.start)} – ${frappe.datetime.str_to_user(p.end)})
				</div>
				<div style="font-size: var(--text-lg); font-weight: 600; margin: 8px 0;">
					${esc(p.invoice_title || "")}
				</div>
				${items}
			</div>`;
	},
};

frappe.ui.form.on("Auto Repeat", {
	refresh(frm) {
		const bp = entre_facturacao.billing_period;
		if (bp.is_invoice(frm)) {
			frm.add_custom_button(
				__("Copiar descrições da factura modelo"),
				() => bp.copy_from_template(frm),
				__("Período de Facturação")
			);
		}
		bp.render_preview(frm);
	},
	billing_mode: (frm) => entre_facturacao.billing_period.render_preview(frm),
	frequency: (frm) => entre_facturacao.billing_period.render_preview(frm),
	start_date: (frm) => entre_facturacao.billing_period.render_preview(frm),
	next_schedule_date: (frm) => entre_facturacao.billing_period.render_preview(frm),
	reference_document: (frm) => entre_facturacao.billing_period.render_preview(frm),
	title_template: (frm) => entre_facturacao.billing_period.render_preview(frm),
	billing_descriptions_remove: (frm) => entre_facturacao.billing_period.render_preview(frm),
});

frappe.ui.form.on("Auto Repeat Descricao", {
	item_idx: (frm) => entre_facturacao.billing_period.render_preview(frm),
	description_template: (frm) => entre_facturacao.billing_period.render_preview(frm),
});
