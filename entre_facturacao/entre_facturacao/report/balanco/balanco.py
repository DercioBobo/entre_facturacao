"""Balanço (modelo do PGC, Decreto n.º 70/2009) numa data, com a mesma data do
ano anterior como período comparativo n-1.

As linhas e as contas de cada linha vêm de Facturação Settings (tabela "Linhas
do Balanço"); se a tabela estiver vazia usa-se LINHAS_PADRAO. Cada conta de
balanço vai, em cada período, para a linha com o prefixo de código mais longo
que lhe corresponda; um prefixo com sufixo + só aceita a conta com saldo
devedor e com - só com saldo credor (ex.: Estado 44+ é activo, 44- é passivo).

O resultado do exercício que ainda está nas contas de gastos e rendimentos
(antes do apuramento) entra na linha marcada "Inclui Resultado do Exercício".
Contas de balanço sem linha vão para "Contas não mapeadas" (no activo se o
saldo for devedor, no passivo se for credor), para que o balanço continue a
fechar e o problema fique visível."""

import frappe
from frappe import _
from frappe.utils import add_years, flt, getdate

from entre_facturacao.entre_facturacao.report.balancete.balancete import condicoes_centro_e_livro
from entre_facturacao.entre_facturacao.report.demonstracao_de_resultados.demonstracao_de_resultados import (
	normalizar,
)

# Modelo do guia do PGC-PE (5.7.1), com os códigos do plano PGC-PE.
# Confirme os códigos com o plano de contas da empresa (PGC-NIRF ou PGC-PE).
LINHAS_PADRAO = [
	{"designacao": "Activos não correntes", "tipo": "Cabeçalho"},
	{"designacao": "Activos tangíveis", "tipo": "Contas", "grupo": "Activo", "contas": "32, 34, 38"},
	{"designacao": "Activos tangíveis de investimento", "tipo": "Contas", "grupo": "Activo", "contas": "36"},
	{"designacao": "Activos intangíveis", "tipo": "Contas", "grupo": "Activo", "contas": "33"},
	{"designacao": "Activos biológicos", "tipo": "Contas", "grupo": "Activo", "contas": ""},
	{"designacao": "Investimentos financeiros", "tipo": "Contas", "grupo": "Activo", "contas": "31, 39"},
	{"designacao": "Outros activos não correntes", "tipo": "Contas", "grupo": "Activo", "contas": ""},
	{"designacao": "Activos correntes", "tipo": "Cabeçalho"},
	{"designacao": "Inventários", "tipo": "Contas", "grupo": "Activo", "contas": "21, 22, 23, 24, 25, 26, 28, 29"},
	{"designacao": "Activos biológicos", "tipo": "Contas", "grupo": "Activo", "contas": "27"},
	{"designacao": "Clientes", "tipo": "Contas", "grupo": "Activo", "contas": "41+, 47"},
	{"designacao": "Outros activos correntes", "tipo": "Contas", "grupo": "Activo", "contas": "42+, 44+, 45+, 46+, 49+"},
	{"designacao": "Caixa e bancos", "tipo": "Contas", "grupo": "Activo", "contas": "11, 12+"},
	{"designacao": "Total dos activos", "tipo": "Total", "total_de": "Activo"},
	{"designacao": "Capital próprio", "tipo": "Cabeçalho"},
	{"designacao": "Capital social", "tipo": "Contas", "grupo": "Capital Próprio", "contas": "51, 52"},
	{"designacao": "Reservas", "tipo": "Contas", "grupo": "Capital Próprio", "contas": "53, 54, 55, 56, 58"},
	{"designacao": "Resultados transitados", "tipo": "Contas", "grupo": "Capital Próprio", "contas": "59"},
	{
		"designacao": "Resultado líquido do período",
		"tipo": "Contas",
		"grupo": "Capital Próprio",
		"contas": "8",
		"inclui_resultado": 1,
	},
	{"designacao": "Total do capital próprio", "tipo": "Total", "total_de": "Capital Próprio"},
	{"designacao": "Passivos não correntes", "tipo": "Cabeçalho"},
	{"designacao": "Provisões", "tipo": "Contas", "grupo": "Passivo", "contas": "48"},
	{"designacao": "Empréstimos obtidos", "tipo": "Contas", "grupo": "Passivo", "contas": "43"},
	{"designacao": "Outros passivos não correntes", "tipo": "Contas", "grupo": "Passivo", "contas": ""},
	{"designacao": "Passivos correntes", "tipo": "Cabeçalho"},
	{"designacao": "Provisões", "tipo": "Contas", "grupo": "Passivo", "contas": ""},
	{"designacao": "Fornecedores", "tipo": "Contas", "grupo": "Passivo", "contas": "42-"},
	{"designacao": "Empréstimos obtidos", "tipo": "Contas", "grupo": "Passivo", "contas": "12-"},
	{"designacao": "Impostos a pagar", "tipo": "Contas", "grupo": "Passivo", "contas": "44-"},
	{"designacao": "Outros passivos correntes", "tipo": "Contas", "grupo": "Passivo", "contas": "41-, 45-, 46-, 49-"},
	{"designacao": "Total dos passivos", "tipo": "Total", "total_de": "Passivo"},
	{"designacao": "Total do capital próprio e dos passivos", "tipo": "Total", "total_de": "Capital Próprio e Passivo"},
]

GRUPOS_DO_TOTAL = {
	"Activo": {"Activo"},
	"Capital Próprio": {"Capital Próprio"},
	"Passivo": {"Passivo"},
	"Capital Próprio e Passivo": {"Capital Próprio", "Passivo"},
}

PERIODOS = ("atual", "anterior")


@frappe.whitelist()
def get_linhas_padrao():
	return LINHAS_PADRAO


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not all(filters.get(f) for f in ("empresa", "ano_fiscal", "data_fim")):
		return get_columns(filters), []

	validate_filters(filters)
	columns = get_columns(filters)
	moeda = frappe.get_cached_value("Company", filters.empresa, "default_currency")
	precisao = frappe.get_precision("GL Entry", "debit") or 2

	linhas = get_linhas()
	contas = {
		c.name: c
		for c in frappe.get_all(
			"Account",
			filters={"company": filters.empresa, "is_group": 0},
			fields=["name", "account_number", "account_name", "report_type"],
		)
	}
	valores = get_valores(filters)
	data, totais, avisos = montar_linhas(linhas, contas, valores, filters, moeda, precisao)

	mensagem = "<br>".join(avisos) if avisos else None
	return columns, data, mensagem, None, get_report_summary(totais, moeda)


def validate_filters(filters):
	ano = frappe.get_cached_value(
		"Fiscal Year", filters.ano_fiscal, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not ano:
		frappe.throw(_("Ano fiscal {0} não encontrado.").format(filters.ano_fiscal))

	filters.ano_inicio = getdate(ano.year_start_date)
	filters.data_fim = getdate(filters.data_fim)
	if not (filters.ano_inicio <= filters.data_fim <= getdate(ano.year_end_date)):
		frappe.throw(_("A data do balanço deve estar dentro do ano fiscal {0}.").format(filters.ano_fiscal))

	# Período n-1: a mesma data um ano antes.
	filters.anterior_ano_inicio = add_years(filters.ano_inicio, -1)
	filters.anterior_fim = add_years(filters.data_fim, -1)


def get_columns(filters):
	def data(d):
		return f" ({frappe.format_value(d, 'Date')})" if filters.get("anterior_fim") else ""

	columns = [
		{"label": _("Designação"), "fieldname": "designacao", "fieldtype": "Data", "width": 380},
		{
			"label": _("Período n") + data(filters.get("data_fim")),
			"fieldname": "atual",
			"fieldtype": "Currency",
			"options": "currency",
			"width": 200,
		},
	]
	if filters.get("comparativo"):
		columns.append(
			{
				"label": _("Período n-1") + data(filters.get("anterior_fim")),
				"fieldname": "anterior",
				"fieldtype": "Currency",
				"options": "currency",
				"width": 200,
			}
		)
	columns.append({"label": _("Moeda"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1})
	return columns


def get_linhas():
	configuradas = frappe.get_all(
		"Linha Balanco",
		filters={"parent": "Facturacao Settings", "parenttype": "Facturacao Settings"},
		fields=["designacao", "tipo", "grupo", "total_de", "contas", "inclui_resultado"],
		order_by="idx",
	)
	linhas = []
	for n, l in enumerate(configuradas or LINHAS_PADRAO):
		l = frappe._dict(l)
		l.chave = f"linha_{n}"
		l.prefixos = []
		for parte in (l.contas or "").split(","):
			parte = parte.strip()
			sinal = parte[-1] if parte[-1:] in ("+", "-") else None
			prefixo = normalizar(parte)
			if prefixo:
				l.prefixos.append((prefixo, sinal))
		linhas.append(l)
	return linhas


def get_valores(filters):
	"""Por conta, em cada período: saldo (débito - crédito) até à data e o
	movimento desde o início do respectivo exercício."""
	condicoes = [
		"gle.company = %(empresa)s",
		"gle.is_cancelled = 0",
		"gle.posting_date <= %(n_fim)s",
	]
	params = {
		"empresa": filters.empresa,
		"n_inicio": filters.ano_inicio,
		"n_fim": filters.data_fim,
		"n1_inicio": filters.anterior_ano_inicio,
		"n1_fim": filters.anterior_fim,
	}
	condicoes += condicoes_centro_e_livro(frappe._dict(empresa=filters.empresa, finance_book=filters.finance_book), params)

	rows = frappe.db.sql(
		f"""
		SELECT gle.account,
			SUM(gle.debit - gle.credit) AS saldo_atual,
			SUM(CASE WHEN gle.posting_date >= %(n_inicio)s
				THEN gle.debit - gle.credit ELSE 0 END) AS exercicio_atual,
			SUM(CASE WHEN gle.posting_date <= %(n1_fim)s
				THEN gle.debit - gle.credit ELSE 0 END) AS saldo_anterior,
			SUM(CASE WHEN gle.posting_date BETWEEN %(n1_inicio)s AND %(n1_fim)s
				THEN gle.debit - gle.credit ELSE 0 END) AS exercicio_anterior
		FROM `tabGL Entry` gle
		WHERE {" AND ".join(condicoes)}
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)
	return {r.account: r for r in rows}


def linha_da_conta(conta, saldo, linhas):
	"""A linha cujo prefixo (o mais longo, respeitando o sinal +/-) corresponde à conta."""
	codigo = normalizar(conta.account_number)
	if not codigo:
		return None
	melhor, tamanho = None, 0
	for l in linhas:
		if l.tipo != "Contas":
			continue
		for prefixo, sinal in l.prefixos:
			if sinal == "+" and saldo <= 0 or sinal == "-" and saldo >= 0:
				continue
			if codigo.startswith(prefixo) and len(prefixo) > tamanho:
				melhor, tamanho = l, len(prefixo)
	return melhor


def montar_linhas(linhas, contas, valores, filters, moeda, precisao):
	periodos = PERIODOS if filters.comparativo else PERIODOS[:1]

	def sintetica(chave, designacao, grupo):
		return frappe._dict(chave=chave, designacao=designacao, tipo="Contas", grupo=grupo, prefixos=[])

	nao_mapeada_activo = sintetica("__nao_mapeadas_activo__", _("Contas não mapeadas (activo)"), "Activo")
	nao_mapeada_passivo = sintetica("__nao_mapeadas_passivo__", _("Contas não mapeadas (passivo)"), "Passivo")
	por_apurar = sintetica(
		"__resultados_por_apurar__", _("Resultados de exercícios anteriores por apurar"), "Capital Próprio"
	)
	linha_resultado = next((l for l in linhas if l.tipo == "Contas" and l.inclui_resultado), None)
	if not linha_resultado:
		linha_resultado = sintetica("__resultado__", _("Resultado líquido do período"), "Capital Próprio")

	# chave da linha -> {conta -> {periodo: saldo devedor}}
	por_linha = {}
	# chave da linha -> {periodo: valor devedor fora de contas (resultados)}
	extra = {}
	nao_mapeadas = set()

	for nome, v in valores.items():
		conta = contas.get(nome)
		if not conta:
			continue
		for p in periodos:
			saldo = flt(v[f"saldo_{p}"], precisao)
			if conta.report_type == "Profit and Loss":
				exercicio = flt(v[f"exercicio_{p}"], precisao)
				extra.setdefault(linha_resultado.chave, {}).setdefault(p, 0.0)
				extra[linha_resultado.chave][p] += exercicio
				extra.setdefault(por_apurar.chave, {}).setdefault(p, 0.0)
				extra[por_apurar.chave][p] += saldo - exercicio
				continue
			if not saldo:
				continue
			linha = linha_da_conta(conta, saldo, linhas)
			if not linha:
				linha = nao_mapeada_activo if saldo > 0 else nao_mapeada_passivo
				nao_mapeadas.add(nome)
			por_linha.setdefault(linha.chave, {}).setdefault(nome, {})[p] = saldo

	# Linhas sintéticas entram antes do primeiro total que cobre o seu grupo.
	ordem = list(linhas)
	for l in (nao_mapeada_activo, nao_mapeada_passivo, por_apurar, linha_resultado):
		if l in ordem:
			continue
		tem_valor = l.chave in por_linha or any(abs(x) >= 0.005 for x in extra.get(l.chave, {}).values())
		if not tem_valor:
			continue
		pos = next(
			(i for i, x in enumerate(ordem) if x.tipo == "Total" and l.grupo in GRUPOS_DO_TOTAL.get(x.total_de, ())),
			len(ordem),
		)
		ordem.insert(pos, l)

	def sinal(grupo):
		return 1 if grupo == "Activo" else -1

	somas = {g: {p: 0.0 for p in PERIODOS} for g in ("Activo", "Capital Próprio", "Passivo")}
	data = []
	for l in ordem:
		linha = {"linha": l.chave, "parent_linha": None, "indent": 0, "designacao": l.designacao, "currency": moeda}

		if l.tipo == "Cabeçalho":
			linha["is_cabecalho"] = 1
			data.append(linha)
			continue

		if l.tipo == "Total":
			grupos = GRUPOS_DO_TOTAL.get(l.total_de, set())
			linha["is_total"] = 1
			for p in PERIODOS:
				linha[p] = flt(sum(somas[g][p] for g in grupos), precisao)
			data.append(linha)
			continue

		s = sinal(l.grupo)
		filhos = []
		for nome, saldos in por_linha.get(l.chave, {}).items():
			conta = contas[nome]
			filhos.append(
				{
					"linha": f"{l.chave}|{nome}",
					"parent_linha": l.chave,
					"indent": 1,
					"account": nome,
					"designacao": " - ".join(filter(None, [conta.account_number, conta.account_name])),
					"currency": moeda,
					**{p: flt(s * saldos.get(p, 0), precisao) for p in PERIODOS},
				}
			)
		filhos.sort(key=lambda r: r["designacao"])

		for p in PERIODOS:
			valor = sum(f[p] for f in filhos) + s * extra.get(l.chave, {}).get(p, 0.0)
			linha[p] = flt(valor, precisao)
			if l.grupo in somas:
				somas[l.grupo][p] += valor
		if l.chave.startswith("__"):
			linha["is_aviso"] = int(l is not linha_resultado)
		data.append(linha)
		data.extend(filhos)

	totais = frappe._dict(
		activo=flt(somas["Activo"]["atual"], precisao),
		capital_e_passivo=flt(somas["Capital Próprio"]["atual"] + somas["Passivo"]["atual"], precisao),
	)

	avisos = []
	if nao_mapeadas:
		lista = sorted(nao_mapeadas)
		avisos.append(
			_("Há contas de balanço que não correspondem a nenhuma linha (ver \"Contas não mapeadas\"). Ajuste as linhas em Facturação Settings: {0}").format(
				", ".join(lista[:10]) + ("…" if len(lista) > 10 else "")
			)
		)
	if any(abs(x) >= 0.005 for x in extra.get(por_apurar.chave, {}).values()):
		avisos.append(
			_("Há resultados de exercícios anteriores sem apuramento (sem Period Closing Voucher); "
			"aparecem em \"Resultados de exercícios anteriores por apurar\".")
		)
	return data, totais, avisos


def get_report_summary(totais, moeda):
	diferenca = flt(totais.activo - totais.capital_e_passivo, 2)
	return [
		{"value": totais.activo, "label": _("Total dos Activos"), "datatype": "Currency", "currency": moeda},
		{
			"value": totais.capital_e_passivo,
			"label": _("Total do Capital Próprio e Passivos"),
			"datatype": "Currency",
			"currency": moeda,
		},
		{
			"value": diferenca,
			"label": _("Diferença"),
			"datatype": "Currency",
			"currency": moeda,
			"indicator": "Green" if abs(diferenca) < 0.005 else "Red",
		},
	]
