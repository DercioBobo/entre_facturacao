frappe.provide("entre_facturacao");

// Funcionalidades ligadas em Facturação Settings (ver entre_facturacao/features.py).
entre_facturacao.feature = function (name) {
	const features = (frappe.boot.entre_facturacao_settings || {}).features || {};
	return !!features[name];
};

entre_facturacao.feature_disabled_html = function (label) {
	return `
		<div class="text-center text-muted" style="padding: 80px 20px;">
			<p style="font-size: var(--text-lg);">${__("A funcionalidade {0} está desligada.", [__(label)])}</p>
			<p><a href="/app/facturacao-settings">${__("Ligar em Facturação Settings")}</a></p>
		</div>`;
};

// Página de uma funcionalidade desligada: mostra o aviso em vez do conteúdo.
entre_facturacao.page_feature_guard = function (wrapper, feature, label) {
	if (entre_facturacao.feature(feature)) return true;
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __(label), single_column: true });
	$(page.body).html(entre_facturacao.feature_disabled_html(label));
	return false;
};

[
	["Agenda de Factura", "feature_agenda_factura", "Agenda de Factura"],
	["Apuramento de IVA", "feature_centro_fiscal", "Centro Fiscal e Apuramento de IVA"],
].forEach(([doctype, feature, label]) => {
	frappe.ui.form.on(doctype, {
		refresh(frm) {
			if (entre_facturacao.feature(feature)) return;
			frm.set_intro(
				__("A funcionalidade {0} está desligada em Facturação Settings. Este documento não pode ser alterado.", [
					__(label),
				]),
				"orange"
			);
			frm.disable_save();
		},
	});
});
