frappe.ui.form.on("Facturacao Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Carregar Modelo PGC"), () => {
			const carregar = () =>
				frappe
					.call("entre_facturacao.entre_facturacao.report.demonstracao_de_resultados.demonstracao_de_resultados.get_linhas_padrao")
					.then(({ message }) => {
						frm.clear_table("linhas_demonstracao_resultados");
						(message || []).forEach((linha) => frm.add_child("linhas_demonstracao_resultados", linha));
						frm.refresh_field("linhas_demonstracao_resultados");
						frm.dirty();
					});
			if ((frm.doc.linhas_demonstracao_resultados || []).length) {
				frappe.confirm(__("Substituir as linhas actuais da Demonstração de Resultados pelo modelo PGC?"), carregar);
			} else {
				carregar();
			}
		});
	},
});
