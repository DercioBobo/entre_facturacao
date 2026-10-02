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

	VARIABLES: [
		["periodo", "Período completo"],
		["mes", "Mês (início do período)"],
		["ano", "Ano (início do período)"],
		["mes_fim", "Último mês do período"],
		["ano_fim", "Ano do último mês"],
		["data_inicio", "Data de início"],
		["data_fim", "Data de fim"],
		["item_name", "Nome do item (só nas descrições)"],
		["item_code", "Código do item (só nas descrições)"],
	],

	render_variables_help(frm, context) {
		const field = frm.get_field("billing_variables_help");
		if (!field) return;
		const esc = frappe.utils.escape_html;
		const ctx = context || {};

		const rows = this.VARIABLES.map(([name, label]) => {
			const tag = `{{ ${name} }}`;
			const example = ctx[name] !== undefined && ctx[name] !== "" ? esc(String(ctx[name])) : "—";
			return `
				<tr>
					<td style="white-space: nowrap;">
						<code class="ef-var" data-var="${esc(tag)}" style="cursor: pointer;"
							title="${__("Clique para copiar")}">${esc(tag)}</code>
					</td>
					<td>${__(label)}</td>
					<td class="text-muted">${example}</td>
				</tr>`;
		}).join("");

		field.$wrapper.html(`
			<div class="small">
				<table class="table table-sm table-bordered" style="margin-bottom: 6px;">
					<thead>
						<tr>
							<th>${__("Variável")}</th>
							<th>${__("Significado")}</th>
							<th>${__("Próxima factura")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
				<div class="text-muted">
					${__("Clique numa variável para a copiar e cole-a no modelo.")}
					${__("Maiúsculas/minúsculas")}: <code>{{ mes|upper }}</code> → ${esc(
						(ctx.mes || "Setembro").toUpperCase()
					)},
					<code>{{ mes|lower }}</code> → ${esc((ctx.mes || "Setembro").toLowerCase())}.
				</div>
			</div>`);

		field.$wrapper.find(".ef-var").on("click", (e) => {
			frappe.utils.copy_to_clipboard($(e.currentTarget).attr("data-var"));
		});
	},

	render_preview(frm) {
		const field = frm.get_field("billing_preview");
		if (!field) return;
		if (!this.is_invoice(frm) || !frm.doc.billing_mode) {
			field.$wrapper.empty();
			return;
		}
		// Static list right away; example values fill in with the preview.
		const help = frm.get_field("billing_variables_help");
		if (help && !help.$wrapper.children().length) this.render_variables_help(frm);

		clearTimeout(this._preview_timer);
		this._preview_timer = setTimeout(() => {
			frappe.call({
				method: "entre_facturacao.billing_period.preview_next_invoice",
				args: { doc: frm.doc },
				callback: (r) => {
					field.$wrapper.html(this.preview_html(r.message));
					if (r.message && r.message.context) {
						this.render_variables_help(frm, r.message.context);
					}
				},
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
					· ${__("Vencimento")}: <b>${p.due_date ? frappe.datetime.str_to_user(p.due_date) : "—"}</b>
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
		if (bp.is_invoice(frm) && !frm.is_new() && !frm.doc.disabled && frm.doc.next_schedule_date) {
			frm.add_custom_button(__("Emitir Agora (Antecipar)"), () =>
				entre_facturacao.auto_repeat.issue_now(frm.doc.name, { on_done: () => frm.reload_doc() })
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
