const APURAMENTO_MESES = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

frappe.ui.form.on("Apuramento de IVA", {
	onload(frm) {
		if (frm.is_new() && !frm.doc.ano) {
			// Por omissão, o mês anterior: é o que normalmente se declara.
			const d = frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1));
			frm.set_value("ano", d.getFullYear());
			frm.set_value("mes", APURAMENTO_MESES[d.getMonth()]);
		}
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
		frm.set_query("lancamento_apuramento", () => ({
			filters: { company: frm.doc.company, docstatus: 1 },
		}));
	},

	refresh(frm) {
		render_avisos(frm);
		render_resultado(frm);
		if (frm.doc.docstatus === 0 && !frm.is_new()) {
			frm.add_custom_button(__("Recalcular"), () => frm.save());
		}
		if (!frm.is_new()) {
			frm.add_custom_button(__("Livro de IVA (Razão)"), () => {
				frappe.route_options = {
					company: frm.doc.company,
					from_date: frm.doc.data_inicio,
					to_date: frm.doc.data_fim,
					account: (frm.doc.reconciliacao || []).map((r) => r.conta),
				};
				frappe.set_route("query-report", "General Ledger");
			});
		}
	},
});

function render_avisos(frm) {
	const avisos = (frm.doc.avisos || "").split("\n").filter(Boolean);
	const html = avisos.length
		? `<div class="alert alert-warning" style="margin-bottom: 0;">
			<b>${__("Verifique antes de submeter")}</b>
			<ul style="margin: 6px 0 0; padding-left: 18px;">
				${avisos.map((a) => `<li>${frappe.utils.escape_html(a)}</li>`).join("")}
			</ul>
		</div>`
		: "";
	frm.get_field("avisos_html").$wrapper.html(html);
}

function render_resultado(frm) {
	if (frm.is_new()) return;
	const fmt = (v) => format_currency(v, erpnext.get_currency(frm.doc.company));
	let texto;
	if (flt(frm.doc.campo_20) > 0) {
		texto = __("IVA a entregar ao Estado: {0} (campo 20). Prazo: {1}.", [
			`<b>${fmt(frm.doc.campo_20)}</b>`,
			frappe.datetime.str_to_user(frm.doc.prazo_entrega),
		]);
		if (frm.doc.docstatus === 1) frm.page.set_indicator(__("A Pagar"), "orange");
	} else if (flt(frm.doc.campo_21) > 0) {
		texto = __("Crédito de imposto: {0} (campo 21), dos quais {1} transitam para o período seguinte.", [
			`<b>${fmt(frm.doc.campo_21)}</b>`,
			fmt(frm.doc.campo_22),
		]);
		if (frm.doc.docstatus === 1) frm.page.set_indicator(__("A Recuperar"), "green");
	} else if (frm.doc.inexistencia_operacoes) {
		texto = __("Sem operações no período (Quadro 04).");
	}
	if (texto) frm.dashboard.set_headline(texto);
}
