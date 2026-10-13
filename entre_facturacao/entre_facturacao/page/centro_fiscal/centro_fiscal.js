frappe.pages["centro-fiscal"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Centro Fiscal"),
		single_column: true,
	});
	wrapper.centro_fiscal = new CentroFiscal(page);
};

frappe.pages["centro-fiscal"].on_page_show = function (wrapper) {
	// Ao voltar de um relatório ou do Apuramento, mostra o estado actualizado.
	if (wrapper.centro_fiscal && wrapper.centro_fiscal.carregado) wrapper.centro_fiscal.carregar();
};

const CF_MESES = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

const CF_ESTADOS = {
	Submetido: { cor: "green", texto: __("Submetido") },
	Rascunho: { cor: "orange", texto: __("Rascunho") },
	"Por criar": { cor: "red", texto: __("Por criar") },
	"Em falta": { cor: "red", texto: __("Em falta") },
	Futuro: { cor: "gray", texto: __("Futuro") },
};

class CentroFiscal {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this.carregado = false;
		cf_estilos();
		this.construir();
	}

	construir() {
		this.$body.html(`
			<div class="cf-wrap">
				<div class="cf-filtros">
					<div class="cf-fg cf-fg--grow" data-campo="empresa"><label>${__("Empresa")}</label></div>
					<div class="cf-fg" data-campo="mes"><label>${__("Mês")}</label></div>
					<div class="cf-fg cf-fg--ano" data-campo="ano"><label>${__("Ano")}</label></div>
				</div>
				<div class="cf-conteudo"></div>
			</div>`);

		// Por omissão o mês anterior: é o que normalmente se declara.
		const anterior = frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1));
		const campo = (fieldname, df) => {
			const control = frappe.ui.form.make_control({
				parent: this.$body.find(`[data-campo="${fieldname}"]`),
				df: { fieldname, ...df, change: () => !this.a_iniciar && this.carregar() },
				render_input: true,
			});
			return control;
		};
		this.empresa = campo("empresa", { fieldtype: "Link", options: "Company" });
		this.mes = campo("mes", { fieldtype: "Select", options: CF_MESES.join("\n") });
		this.ano = campo("ano", { fieldtype: "Int" });

		this.a_iniciar = true;
		this.empresa.set_value(frappe.defaults.get_user_default("Company") || "");
		this.mes.set_value(CF_MESES[anterior.getMonth()]);
		this.ano.set_value(anterior.getFullYear());

		this.page.set_secondary_action(__("Actualizar"), () => this.carregar(), "refresh");
		this.page.add_menu_item(__("Facturação Settings"), () => frappe.set_route("Form", "Facturacao Settings"));

		this.$body.on("click", "[data-accao]", (e) => {
			e.preventDefault();
			this.accao($(e.currentTarget).data("accao"), $(e.currentTarget).data());
		});
		setTimeout(() => {
			this.a_iniciar = false;
			this.carregar();
		}, 0);
	}

	filtros() {
		return {
			empresa: this.empresa.get_value(),
			mes: CF_MESES.indexOf(this.mes.get_value()) + 1,
			ano: cint(this.ano.get_value()),
		};
	}

	carregar() {
		const f = this.filtros();
		if (!f.empresa || !f.mes || !f.ano) return;
		const pedido = (this.pedido = {});
		this.$body.find(".cf-conteudo").html(`<div class="cf-a-carregar">${__("A calcular...")}</div>`);
		frappe
			.call("entre_facturacao.entre_facturacao.page.centro_fiscal.centro_fiscal.get_estado", {
				empresa: f.empresa,
				ano: f.ano,
				mes: f.mes,
			})
			.then(({ message }) => {
				if (pedido !== this.pedido) return; // chegou entretanto um pedido mais recente
				this.carregado = true;
				this.estado = message;
				this.render(message);
			});
	}

	fmt(valor) {
		return format_currency(valor, this.estado.moeda);
	}

	render(e) {
		const nome_mes = `${this.mes.get_value()} ${this.ano.get_value()}`;
		this.$body.find(".cf-conteudo").html(`
			${this.render_configuracao(e.configuracao)}
			<div class="cf-seccao">${__("Mensal")} · ${frappe.utils.escape_html(nome_mes)}</div>
			<div class="cf-grelha">
				${this.render_iva(e.iva)}
				${this.render_balancete(e.balancete)}
			</div>
			<div class="cf-seccao">${__("Exercício")} ${frappe.utils.escape_html(e.ano_fiscal || "")}
				· ${__("até")} ${frappe.datetime.str_to_user(e.fim)}</div>
			<div class="cf-grelha">
				${this.render_balanco(e.balanco)}
				${this.render_demonstracao(e.demonstracao)}
			</div>
			${this.render_historico(e.historico_iva)}
		`);
	}

	render_configuracao(c) {
		if (c.erro) return this.alerta([c.erro]);
		if (!c.avisos.length) return "";
		const destinos = {
			settings: `<a href="#" data-accao="settings">${__("Corrigir")}</a>`,
			company: `<a href="#" data-accao="empresa">${__("Abrir empresa")}</a>`,
		};
		return `<div class="cf-alerta">
			<b>${__("Configuração")}</b>
			<ul>${c.avisos.map((a) => `<li>${frappe.utils.escape_html(a.texto)} ${destinos[a.destino] || ""}</li>`).join("")}</ul>
		</div>`;
	}

	cartao({ titulo, estado, cor, linhas, avisos, accoes }) {
		const avisos_html = (avisos || []).length
			? `<ul class="cf-avisos">${avisos.map((a) => `<li>${frappe.utils.escape_html(a)}</li>`).join("")}</ul>`
			: "";
		return `<div class="cf-cartao">
			<div class="cf-cartao-topo">
				<span class="cf-cartao-titulo">${titulo}</span>
				${estado ? `<span class="indicator-pill ${cor}">${estado}</span>` : ""}
			</div>
			<div class="cf-linhas">${linhas.map(([k, v, classe]) => `
				<div class="cf-linha"><span>${k}</span><span class="${classe || ""}">${v}</span></div>`).join("")}
			</div>
			${avisos_html}
			<div class="cf-accoes">${accoes.join("")}</div>
		</div>`;
	}

	botao(texto, accao, dados = {}, primario = false) {
		const attrs = Object.entries(dados)
			.map(([k, v]) => `data-${k}="${frappe.utils.escape_html(String(v))}"`)
			.join(" ");
		return `<button class="btn btn-xs ${primario ? "btn-primary" : "btn-default"}" data-accao="${accao}" ${attrs}>${texto}</button>`;
	}

	erro(titulo, mensagem) {
		return this.cartao({ titulo, estado: __("Erro"), cor: "red", linhas: [[frappe.utils.escape_html(mensagem), ""]], accoes: [] });
	}

	render_iva(i) {
		if (i.erro) return this.erro(__("Apuramento de IVA"), i.erro);
		const e = CF_ESTADOS[i.estado];
		const linhas = [];
		const estimativa = i.estado === "Por criar" ? ` <span class="text-muted">(${__("estimativa")})</span>` : "";
		if (i.a_pagar > 0) {
			linhas.push([__("IVA a entregar (campo 20)") + estimativa, this.fmt(i.a_pagar), "cf-forte"]);
		} else if (i.credito > 0) {
			linhas.push([__("Crédito de imposto (campo 21)") + estimativa, this.fmt(i.credito), "cf-forte"]);
			linhas.push([__("Reporte para o mês seguinte (campo 22)"), this.fmt(i.reporte)]);
		} else {
			linhas.push([__("Resultado") + estimativa, i.sem_operacoes ? __("Sem operações") : this.fmt(0)]);
		}
		let prazo = frappe.datetime.str_to_user(i.prazo);
		if (i.estado !== "Submetido") {
			const d = i.dias_para_prazo;
			prazo += d < 0
				? ` <span class="cf-mau">(${__("{0} dias de atraso", [-d])})</span>`
				: ` <span class="${d <= 7 ? "cf-atencao" : "text-muted"}">(${__("faltam {0} dias", [d])})</span>`;
		}
		linhas.push([__("Prazo de entrega"), prazo]);

		const accoes = i.nome
			? [this.botao(__("Abrir"), "abrir_iva", { nome: i.nome }, true), this.botao(__("Imprimir Modelo A"), "imprimir_iva", { nome: i.nome })]
			: [this.botao(__("Criar Apuramento"), "criar_iva", {}, true)];
		return this.cartao({ titulo: __("Apuramento de IVA"), estado: e.texto, cor: e.cor, linhas, avisos: i.avisos, accoes });
	}

	equilibrio(diferenca, texto_ok) {
		return Math.abs(diferenca) < 0.005
			? { estado: texto_ok, cor: "green" }
			: { estado: __("Diferença {0}", [this.fmt(diferenca)]), cor: "red" };
	}

	render_balancete(b) {
		if (b.erro) return this.erro(__("Balancete"), b.erro);
		return this.cartao({
			titulo: __("Balancete"),
			...this.equilibrio(b.diferenca, __("Equilibrado")),
			linhas: [
				[__("Total saldos devedores"), this.fmt(b.devedor)],
				[__("Total saldos credores"), this.fmt(b.credor)],
			],
			avisos: b.avisos,
			accoes: [this.botao(__("Abrir"), "relatorio", { relatorio: "Balancete", chave: "balancete" }, true)],
		});
	}

	render_balanco(b) {
		if (b.erro) return this.erro(__("Balanço"), b.erro);
		const linhas = [[__("Total dos activos"), this.fmt(b.activo)]];
		linhas.push([__("Contas não mapeadas"), b.nao_mapeadas ? `<span class="cf-mau">${b.nao_mapeadas}</span>` : "0"]);
		return this.cartao({
			titulo: __("Balanço"),
			...this.equilibrio(b.diferenca, __("Fecha")),
			linhas,
			avisos: b.avisos,
			accoes: [this.botao(__("Abrir"), "relatorio", { relatorio: "Balanco", chave: "balanco" }, true)],
		});
	}

	render_demonstracao(d) {
		if (d.erro) return this.erro(__("Demonstração de Resultados"), d.erro);
		const ok = !d.nao_mapeadas;
		return this.cartao({
			titulo: __("Demonstração de Resultados"),
			estado: ok ? __("Completa") : __("Contas não mapeadas"),
			cor: ok ? "green" : "red",
			linhas: [
				[__("Resultado líquido do exercício"), this.fmt(d.resultado), d.resultado < 0 ? "cf-mau cf-forte" : "cf-forte"],
				[__("Contas não mapeadas"), d.nao_mapeadas ? `<span class="cf-mau">${d.nao_mapeadas}</span>` : "0"],
			],
			avisos: d.avisos,
			accoes: [this.botao(__("Abrir"), "relatorio", { relatorio: "Demonstracao de Resultados", chave: "demonstracao" }, true)],
		});
	}

	render_historico(h) {
		if (h.erro) return "";
		const mes_actual = this.filtros().mes;
		return `<div class="cf-seccao">${__("Histórico do IVA")} · ${this.ano.get_value()}</div>
			<div class="cf-historico">${h.meses.map((m) => {
				const e = CF_ESTADOS[m.estado];
				return `<a href="#" class="cf-mes cf-mes--${e.cor} ${m.mes === mes_actual ? "cf-mes--actual" : ""}"
					data-accao="mes" data-mes="${m.mes}" title="${e.texto}">
					<span>${__(m.nome_mes).substring(0, 3)}</span><small>${e.texto}</small></a>`;
			}).join("")}</div>`;
	}

	accao(accao, dados) {
		const f = this.filtros();
		if (accao === "abrir_iva") {
			frappe.set_route("Form", "Apuramento de IVA", dados.nome);
		} else if (accao === "imprimir_iva") {
			const params = new URLSearchParams({ doctype: "Apuramento de IVA", name: dados.nome, format: "Modelo A IVA" });
			window.open(`/printview?${params}`, "_blank");
		} else if (accao === "criar_iva") {
			frappe.new_doc("Apuramento de IVA", { company: f.empresa, ano: f.ano, mes: CF_MESES[f.mes - 1] });
		} else if (accao === "relatorio") {
			frappe.route_options = this.estado[dados.chave].filtros;
			frappe.set_route("query-report", dados.relatorio);
		} else if (accao === "mes") {
			this.mes.set_value(CF_MESES[dados.mes - 1]);
		} else if (accao === "settings") {
			frappe.set_route("Form", "Facturacao Settings");
		} else if (accao === "empresa") {
			frappe.set_route("Form", "Company", f.empresa);
		}
	}

	alerta(linhas) {
		return `<div class="cf-alerta"><ul>${linhas.map((l) => `<li>${frappe.utils.escape_html(l)}</li>`).join("")}</ul></div>`;
	}
}

function cf_estilos() {
	if (document.getElementById("cf-css")) return;
	const s = document.createElement("style");
	s.id = "cf-css";
	s.textContent = `
.cf-wrap { padding: 16px 20px; max-width: 1100px; }
.cf-filtros { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; background: var(--fg-color);
	border: 1px solid var(--border-color); border-radius: 10px; padding: 12px 16px; margin-bottom: 16px; }
.cf-fg { display: flex; flex-direction: column; gap: 4px; min-width: 140px; }
.cf-fg--grow { flex: 1; min-width: 220px; }
.cf-fg--ano { min-width: 90px; max-width: 110px; }
.cf-fg > label { font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase;
	letter-spacing: .5px; margin: 0; }
.cf-fg .form-group { margin-bottom: 0 !important; }
.cf-fg label.control-label, .cf-fg .help-box { display: none !important; }

.cf-alerta { background: var(--alert-bg-warning, #fff8e6); color: var(--alert-text-warning, #7a5300);
	border: 1px solid var(--yellow-300, #f5d58a); border-radius: 10px; padding: 10px 16px; margin-bottom: 16px; }
.cf-alerta ul { margin: 4px 0 0; padding-left: 18px; }
.cf-alerta a { font-weight: 600; margin-left: 6px; }

.cf-seccao { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px;
	color: var(--text-muted); margin: 18px 0 8px; }
.cf-grelha { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 14px; }
.cf-cartao { background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 10px;
	padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.cf-cartao-topo { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.cf-cartao-titulo { font-size: 15px; font-weight: 600; color: var(--heading-color, var(--text-color)); }
.cf-linhas { display: flex; flex-direction: column; gap: 6px; }
.cf-linha { display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }
.cf-linha > span:first-child { color: var(--text-muted); }
.cf-linha > span:last-child { text-align: right; font-variant-numeric: tabular-nums; }
.cf-forte { font-weight: 700; color: var(--text-color); }
.cf-mau { color: var(--red-600, #c0392b); font-weight: 600; }
.cf-atencao { color: var(--orange-600, #c26b00); font-weight: 600; }
.cf-avisos { margin: 0; padding: 8px 10px 8px 26px; font-size: 12px; background: var(--subtle-fg, var(--control-bg));
	border-radius: 6px; color: var(--text-muted); }
.cf-accoes { display: flex; gap: 6px; flex-wrap: wrap; margin-top: auto; }

.cf-historico { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 6px; }
.cf-mes { display: flex; flex-direction: column; align-items: center; gap: 2px; padding: 8px 2px; border-radius: 8px;
	border: 1px solid var(--border-color); background: var(--fg-color); text-decoration: none !important;
	color: var(--text-color); font-weight: 600; font-size: 13px; border-top-width: 4px; }
.cf-mes small { font-size: 10px; font-weight: 500; color: var(--text-muted); white-space: nowrap; overflow: hidden;
	text-overflow: ellipsis; max-width: 100%; }
.cf-mes--green { border-top-color: var(--green-500, #2e9e5b); }
.cf-mes--orange { border-top-color: var(--orange-500, #e8890c); }
.cf-mes--red { border-top-color: var(--red-500, #e24c4c); }
.cf-mes--gray { border-top-color: var(--gray-300, #ccc); color: var(--text-muted); }
.cf-mes--actual { box-shadow: 0 0 0 2px var(--primary); }
.cf-a-carregar { padding: 40px; text-align: center; color: var(--text-muted); }
@media (max-width: 720px) {
	.cf-wrap { padding: 12px; }
	.cf-historico { grid-template-columns: repeat(6, minmax(0, 1fr)); }
}
`;
	document.head.appendChild(s);
}
