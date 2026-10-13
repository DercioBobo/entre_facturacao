const MODELOS_PGC = {
	linhas_demonstracao_resultados: {
		label: "Demonstração de Resultados",
		method: "entre_facturacao.entre_facturacao.report.demonstracao_de_resultados.demonstracao_de_resultados.get_linhas_padrao",
	},
	linhas_balanco: {
		label: "Balanço",
		method: "entre_facturacao.entre_facturacao.report.balanco.balanco.get_linhas_padrao",
	},
};

function carregar_modelo_pgc(frm, tabela) {
	const { label, method } = MODELOS_PGC[tabela];
	const carregar = () =>
		frappe.call(method).then(({ message }) => {
			frm.clear_table(tabela);
			(message || []).forEach((linha) => frm.add_child(tabela, linha));
			frm.refresh_field(tabela);
			frm.dirty();
		});
	if ((frm.doc[tabela] || []).length) {
		frappe.confirm(__("Substituir as linhas actuais do {0} pelo modelo PGC?", [__(label)]), carregar);
	} else {
		carregar();
	}
}

// Junta as sugestões às linhas existentes: o que já está na tabela (e foi revisto) não é alterado.
function detectar_configuracao_iva(frm) {
	frappe
		.call({
			method: "entre_facturacao.iva_modelo_a.detectar",
			freeze: true,
			freeze_message: __("A analisar os modelos de impostos..."),
		})
		.then(({ message }) => {
			const contas = new Set((frm.doc.iva_contas || []).map((r) => r.conta));
			const modelos = new Set((frm.doc.iva_modelos || []).map((r) => `${r.tipo_modelo}|${r.modelo}`));
			const novas_contas = message.contas.filter((r) => !contas.has(r.conta));
			const novos_modelos = message.modelos.filter((r) => !modelos.has(`${r.tipo_modelo}|${r.modelo}`));

			novas_contas.forEach((r) => frm.add_child("iva_contas", r));
			novos_modelos.forEach((r) => frm.add_child("iva_modelos", r));
			frm.refresh_field("iva_contas");
			frm.refresh_field("iva_modelos");

			if (!novas_contas.length && !novos_modelos.length) {
				frappe.msgprint(__("Nada de novo: as tabelas já têm todas as contas e modelos detectados."));
				return;
			}
			frm.dirty();
			const lista = (linhas, fmt) => linhas.map((r) => `<li>${frappe.utils.escape_html(fmt(r))}</li>`).join("");
			frappe.msgprint({
				title: __("Configuração de IVA detectada"),
				indicator: "blue",
				message: `
					${novas_contas.length ? `<p><b>${__("Contas acrescentadas")}</b></p><ul>${lista(novas_contas, (r) => `${r.conta}: ${__(r.tipo)}`)}</ul>` : ""}
					${novos_modelos.length ? `<p><b>${__("Modelos acrescentados")}</b></p><ul>${lista(novos_modelos, (r) => `${r.modelo}: ${__(r.campo)}`)}</ul>` : ""}
					<p>${__("Reveja as linhas (sobretudo as contas marcadas como \"Não é IVA\" e os modelos isentos 03/04) e grave.")}</p>`,
			});
		});
}

frappe.ui.form.on("Facturacao Settings", {
	refresh(frm) {
		Object.entries(MODELOS_PGC).forEach(([tabela, { label }]) => {
			frm.add_custom_button(__(label), () => carregar_modelo_pgc(frm, tabela), __("Carregar Modelo PGC"));
		});
		frm.add_custom_button(__("Detectar Configuração de IVA"), () => detectar_configuracao_iva(frm));
	},
});
