"""Demonstração de Resultados por natureza (modelo do PGC, Decreto n.º 70/2009),
com o período n e o período comparativo n-1.

As linhas e as contas de cada linha vêm de Facturação Settings (tabela "Linhas
da Demonstração de Resultados"); se a tabela estiver vazia usa-se LINHAS_PADRAO.
Cada conta de movimento vai para a linha com o prefixo de código mais longo que
lhe corresponda. Rendimentos aparecem positivos e gastos negativos, pelo que um
Subtotal é a soma simples de todas as linhas acima dele.

As contas de resultados (Profit and Loss) que não caibam em nenhuma linha vão
para "Contas não mapeadas", para que o resultado líquido continue certo e o
problema fique visível. O apuramento de resultados (Period Closing Voucher)
nunca entra, senão as contas de resultados apareceriam a zero."""

import re

import frappe
from frappe import _
from frappe.utils import add_years, flt, getdate

from entre_facturacao.entre_facturacao.report.balancete.balancete import condicoes_centro_e_livro

# Modelo "Por natureza" do guia do PGC-PE (5.7.2), com os códigos do plano PGC-PE.
# Confirme os códigos com o plano de contas da empresa (PGC-NIRF ou PGC-PE).
LINHAS_PADRAO = [
	{"designacao": "Vendas de bens e de serviços", "tipo": "Contas", "contas": "71, 72"},
	{"designacao": "Variação da produção e de trabalhos em curso", "tipo": "Contas", "contas": ""},
	{"designacao": "Investimentos realizados pela própria empresa", "tipo": "Contas", "contas": "73"},
	{"designacao": "Custo dos inventários vendidos ou consumidos", "tipo": "Contas", "contas": "61"},
	{"designacao": "Custos com o pessoal", "tipo": "Contas", "contas": "62"},
	{"designacao": "Fornecimentos e serviços de terceiros", "tipo": "Contas", "contas": "63"},
	{"designacao": "Amortizações", "tipo": "Contas", "contas": "65"},
	{"designacao": "Provisões", "tipo": "Contas", "contas": "66"},
	{"designacao": "Ajustamentos de inventários e de contas a receber", "tipo": "Contas", "contas": "64, 74"},
	{"designacao": "Outros ganhos e perdas operacionais", "tipo": "Contas", "contas": "68, 75, 76"},
	{"designacao": "Rendimentos financeiros", "tipo": "Contas", "contas": "78"},
	{"designacao": "Gastos financeiros", "tipo": "Contas", "contas": "69"},
	{"designacao": "Ganhos/perdas imputados de associadas", "tipo": "Contas", "contas": ""},
	{"designacao": "Resultados antes de impostos", "tipo": "Subtotal", "contas": ""},
	{"designacao": "Imposto sobre o rendimento", "tipo": "Contas", "contas": "85"},
	{"designacao": "Resultados líquidos do período", "tipo": "Subtotal", "contas": ""},
]

LINHA_NAO_MAPEADA = "__nao_mapeadas__"


@frappe.whitelist()
def get_linhas_padrao():
	return LINHAS_PADRAO


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not all(filters.get(f) for f in ("empresa", "ano_fiscal", "data_inicio", "data_fim")):
		return get_columns(filters), []

	validate_filters(filters)
	columns = get_columns(filters)
	moeda = frappe.get_cached_value("Company", filters.empresa, "default_currency")
	precisao = frappe.get_precision("GL Entry", "debit") or 2

	linhas = get_linhas()
	contas = get_contas_de_movimento(filters.empresa)
	valores = get_valores(filters)
	data, resultado, nao_mapeadas = montar_linhas(linhas, contas, valores, filters, moeda, precisao)

	mensagem = None
	if nao_mapeadas:
		mensagem = _(
			"Há contas de resultados que não correspondem a nenhuma linha (ver \"Contas não mapeadas\"). "
			"Ajuste as linhas em Facturação Settings: {0}"
		).format(", ".join(nao_mapeadas[:10]) + ("…" if len(nao_mapeadas) > 10 else ""))

	return columns, data, mensagem, None, get_report_summary(resultado, filters, moeda)


def validate_filters(filters):
	ano = frappe.get_cached_value(
		"Fiscal Year", filters.ano_fiscal, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not ano:
		frappe.throw(_("Ano fiscal {0} não encontrado.").format(filters.ano_fiscal))

	filters.data_inicio = getdate(filters.data_inicio)
	filters.data_fim = getdate(filters.data_fim)
	if filters.data_inicio > filters.data_fim:
		frappe.throw(_("A data de início não pode ser posterior à data de fim."))
	if filters.data_inicio < getdate(ano.year_start_date) or filters.data_fim > getdate(ano.year_end_date):
		frappe.throw(_("O período deve estar dentro do ano fiscal {0}.").format(filters.ano_fiscal))

	# Período n-1: as mesmas datas um ano antes.
	filters.anterior_inicio = add_years(filters.data_inicio, -1)
	filters.anterior_fim = add_years(filters.data_fim, -1)


def get_columns(filters):
	def periodo(inicio, fim):
		return f"{frappe.format_value(inicio, 'Date')} – {frappe.format_value(fim, 'Date')}"

	columns = [
		{"label": _("Designação"), "fieldname": "designacao", "fieldtype": "Data", "width": 380},
		{
			"label": _("Período n") + (f" ({periodo(filters.data_inicio, filters.data_fim)})" if filters.get("anterior_inicio") else ""),
			"fieldname": "atual",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 220,
		},
	]
	if filters.get("comparativo"):
		columns.append(
			{
				"label": _("Período n-1") + (f" ({periodo(filters.anterior_inicio, filters.anterior_fim)})" if filters.get("anterior_inicio") else ""),
				"fieldname": "anterior",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 220,
			}
		)
	columns.append({"label": _("Moeda"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1})
	return columns


def normalizar(codigo):
	return re.sub(r"\D", "", codigo or "")


def get_linhas():
	configuradas = frappe.get_all(
		"Linha Demonstracao Resultados",
		filters={"parent": "Facturacao Settings", "parenttype": "Facturacao Settings"},
		fields=["designacao", "tipo", "contas"],
		order_by="idx",
	)
	linhas = []
	for n, l in enumerate(configuradas or LINHAS_PADRAO):
		l = frappe._dict(l)
		l.chave = f"linha_{n}"
		l.prefixos = [p for p in (normalizar(x) for x in (l.contas or "").split(",")) if p]
		linhas.append(l)
	return linhas


def get_contas_de_movimento(empresa):
	return {
		c.name: c
		for c in frappe.get_all(
			"Account",
			filters={"company": empresa, "is_group": 0},
			fields=["name", "account_number", "account_name", "report_type"],
		)
	}


def get_valores(filters):
	"""Por conta: rendimento líquido (crédito - débito) no período n e no n-1."""
	condicoes = [
		"gle.company = %(empresa)s",
		"gle.is_cancelled = 0",
		"gle.is_opening != 'Yes'",
		"gle.voucher_type != 'Period Closing Voucher'",
		"gle.posting_date BETWEEN %(desde)s AND %(ate)s",
	]
	params = {
		"empresa": filters.empresa,
		"n_inicio": filters.data_inicio,
		"n_fim": filters.data_fim,
		"n1_inicio": filters.anterior_inicio,
		"n1_fim": filters.anterior_fim,
		"desde": filters.anterior_inicio if filters.comparativo else filters.data_inicio,
		"ate": filters.data_fim,
	}
	condicoes += condicoes_centro_e_livro(filters, params)

	rows = frappe.db.sql(
		f"""
		SELECT gle.account,
			SUM(CASE WHEN gle.posting_date BETWEEN %(n_inicio)s AND %(n_fim)s
				THEN gle.credit - gle.debit ELSE 0 END) AS atual,
			SUM(CASE WHEN gle.posting_date BETWEEN %(n1_inicio)s AND %(n1_fim)s
				THEN gle.credit - gle.debit ELSE 0 END) AS anterior
		FROM `tabGL Entry` gle
		WHERE {" AND ".join(condicoes)}
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)
	return {r.account: r for r in rows}


def linha_da_conta(conta, linhas):
	"""A linha cujo prefixo (o mais longo) corresponde ao código da conta."""
	codigo = normalizar(conta.account_number)
	if not codigo:
		return None
	melhor, tamanho = None, 0
	for l in linhas:
		if l.tipo == "Subtotal":
			continue
		for p in l.prefixos:
			if codigo.startswith(p) and len(p) > tamanho:
				melhor, tamanho = l, len(p)
	return melhor


def montar_linhas(linhas, contas, valores, filters, moeda, precisao):
	nao_mapeada = frappe._dict(
		chave=LINHA_NAO_MAPEADA, designacao=_("Contas não mapeadas"), tipo="Contas", prefixos=[]
	)
	filhos = {l.chave: [] for l in linhas}
	filhos[LINHA_NAO_MAPEADA] = []
	nao_mapeadas = []

	for nome, v in valores.items():
		conta = contas.get(nome)
		if not conta:
			continue
		linha = linha_da_conta(conta, linhas)
		if not linha:
			if conta.report_type != "Profit and Loss":
				continue
			linha = nao_mapeada
		atual = flt(v.atual, precisao)
		anterior = flt(v.anterior, precisao) if filters.comparativo else 0
		if not (atual or anterior):
			continue
		if linha is nao_mapeada:
			nao_mapeadas.append(nome)
		filhos[linha.chave].append(
			{
				"linha": nome,
				"parent_linha": linha.chave,
				"indent": 1,
				"account": nome,
				"designacao": " - ".join(filter(None, [conta.account_number, conta.account_name])),
				"atual": atual,
				"anterior": anterior,
				"currency": moeda,
			}
		)

	# As contas não mapeadas entram antes do primeiro subtotal, para que este as inclua.
	ordem = list(linhas)
	if filhos[LINHA_NAO_MAPEADA]:
		pos = next((i for i, l in enumerate(ordem) if l.tipo == "Subtotal"), len(ordem))
		ordem.insert(pos, nao_mapeada)

	data = []
	acumulado_atual = acumulado_anterior = 0.0
	for l in ordem:
		if l.tipo == "Subtotal":
			data.append(
				{
					"linha": l.chave,
					"parent_linha": None,
					"indent": 0,
					"is_subtotal": 1,
					"designacao": l.designacao,
					"atual": flt(acumulado_atual, precisao),
					"anterior": flt(acumulado_anterior, precisao),
					"currency": moeda,
				}
			)
			continue

		contas_da_linha = sorted(filhos[l.chave], key=lambda r: r["designacao"])
		atual = sum(r["atual"] for r in contas_da_linha)
		anterior = sum(r["anterior"] for r in contas_da_linha)
		acumulado_atual += atual
		acumulado_anterior += anterior
		data.append(
			{
				"linha": l.chave,
				"parent_linha": None,
				"indent": 0,
				"is_nao_mapeada": int(l.chave == LINHA_NAO_MAPEADA),
				"designacao": l.designacao,
				"atual": flt(atual, precisao),
				"anterior": flt(anterior, precisao),
				"currency": moeda,
			}
		)
		data.extend(contas_da_linha)

	resultado = frappe._dict(atual=flt(acumulado_atual, precisao), anterior=flt(acumulado_anterior, precisao))
	return data, resultado, nao_mapeadas


def get_report_summary(resultado, filters, moeda):
	def cartao(valor, label):
		return {
			"value": valor,
			"label": label,
			"datatype": "Currency",
			"currency": moeda,
			"indicator": "Green" if valor >= 0 else "Red",
		}

	summary = [cartao(resultado.atual, _("Resultado Líquido (Período n)"))]
	if filters.comparativo:
		summary.append(cartao(resultado.anterior, _("Resultado Líquido (Período n-1)")))
	return summary
