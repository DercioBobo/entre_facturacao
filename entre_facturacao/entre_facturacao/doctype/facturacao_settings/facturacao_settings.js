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

frappe.ui.form.on("Facturacao Settings", {
	refresh(frm) {
		Object.entries(MODELOS_PGC).forEach(([tabela, { label }]) => {
			frm.add_custom_button(__(label), () => carregar_modelo_pgc(frm, tabela), __("Carregar Modelo PGC"));
		});
	},
});
