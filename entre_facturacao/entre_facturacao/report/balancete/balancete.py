"""Balancete de Verificação (PGC-NIRF, Decreto n.º 70/2009): por conta do plano,
o saldo inicial, os movimentos do período, os valores acumulados desde o início
do exercício e o saldo final, sempre separados em débito e crédito.

- Saldo Inicial: saldo líquido no dia anterior a "De". Para contas de balanço
  inclui os exercícios anteriores; para contas de resultados (classes 6 e 7)
  começa a zero no início do exercício.
- Movimentos do Período: débitos e créditos entre "De" e "Até".
- Acumulado: saldo de abertura do exercício (no lado do seu sinal) mais todos os
  débitos/créditos desde o início do exercício até "Até".
- Saldo Final: Acumulado Débito - Acumulado Crédito, no lado devedor ou credor.

As contas agregadoras somam as contas filhas. Os totais são calculados sobre as
contas de topo do plano, pelo que Total Devedor = Total Credor quando o
balancete está equilibrado."""

import frappe
from frappe import _
from frappe.utils import flt, getdate

CAMPOS_VALOR = (
	"saldo_inicial_debito",
	"saldo_inicial_credito",
	"movimento_debito",
	"movimento_credito",
	"acumulado_debito",
	"acumulado_credito",
	"saldo_devedor",
	"saldo_credor",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = get_columns()
	if not all(filters.get(f) for f in ("empresa", "ano_fiscal", "data_inicio", "data_fim")):
		return columns, []

	validate_filters(filters)
	moeda = frappe.get_cached_value("Company", filters.empresa, "default_currency")
	precisao = frappe.get_precision("GL Entry", "debit") or 2

	contas = get_contas(filters.empresa)
	if not contas:
		return columns, []

	resultado_por_apurar = calcular_saldos(contas, get_movimentos(filters), precisao)
	data, totais = montar_linhas(contas, filters, moeda, precisao)

	mensagem = None
	if abs(resultado_por_apurar) >= 0.005:
		mensagem = _(
			"Existem {0} de resultados de exercícios anteriores sem apuramento (sem Period Closing Voucher). "
			"O balancete não fica equilibrado enquanto esses exercícios não forem encerrados."
		).format(frappe.format_value(resultado_por_apurar, {"fieldtype": "Currency", "options": moeda}))

	return columns, data, mensagem, None, get_report_summary(totais, moeda)


def validate_filters(filters):
	ano = frappe.get_cached_value(
		"Fiscal Year", filters.ano_fiscal, ["year_start_date", "year_end_date"], as_dict=True
	)
	if not ano:
		frappe.throw(_("Ano fiscal {0} não encontrado.").format(filters.ano_fiscal))

	filters.ano_inicio = getdate(ano.year_start_date)
	filters.ano_fim = getdate(ano.year_end_date)
	filters.data_inicio = getdate(filters.data_inicio)
	filters.data_fim = getdate(filters.data_fim)

	if filters.data_inicio > filters.data_fim:
		frappe.throw(_("A data de início não pode ser posterior à data de fim."))
	if filters.data_inicio < filters.ano_inicio or filters.data_fim > filters.ano_fim:
		frappe.throw(_("O período deve estar dentro do ano fiscal {0}.").format(filters.ano_fiscal))


def get_columns():
	def valor(label, fieldname):
		return {
			"label": label,
			"fieldname": fieldname,
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		}

	return [
		{"label": _("Conta"), "fieldname": "conta", "fieldtype": "Data", "width": 130},
		{"label": _("Designação"), "fieldname": "designacao", "fieldtype": "Data", "width": 260},
		valor(_("Saldo Inicial Débito"), "saldo_inicial_debito"),
		valor(_("Saldo Inicial Crédito"), "saldo_inicial_credito"),
		valor(_("Movimento Débito"), "movimento_debito"),
		valor(_("Movimento Crédito"), "movimento_credito"),
		valor(_("Acumulado Débito"), "acumulado_debito"),
		valor(_("Acumulado Crédito"), "acumulado_credito"),
		valor(_("Saldo Devedor"), "saldo_devedor"),
		valor(_("Saldo Credor"), "saldo_credor"),
		{"label": _("Moeda"), "fieldname": "currency", "fieldtype": "Link", "options": "Currency", "hidden": 1},
	]


def get_contas(empresa):
	"""Contas da empresa, ordenadas como no plano (por código, em profundidade),
	com o nível de cada conta na árvore (0 = conta de topo)."""
	rows = frappe.get_all(
		"Account",
		filters={"company": empresa},
		fields=["name", "account_number", "account_name", "parent_account", "is_group", "report_type"],
	)
	por_nome = {r.name: r for r in rows}
	filhos = {}
	for r in rows:
		pai = r.parent_account if r.parent_account in por_nome else None
		r.parent_account = pai
		filhos.setdefault(pai, []).append(r)

	def chave(r):
		return (r.account_number or "", r.account_name or "")

	ordenadas = {}

	def visitar(conta, nivel):
		conta.nivel = nivel
		ordenadas[conta.name] = conta
		for filho in sorted(filhos.get(conta.name, []), key=chave):
			visitar(filho, nivel + 1)

	for raiz in sorted(filhos.get(None, []), key=chave):
		visitar(raiz, 0)
	return ordenadas


def get_movimentos(filters):
	condicoes = [
		"gle.company = %(empresa)s",
		"gle.is_cancelled = 0",
		"gle.posting_date <= %(data_fim)s",
	]
	params = {
		"empresa": filters.empresa,
		"ano_inicio": filters.ano_inicio,
		"data_inicio": filters.data_inicio,
		"data_fim": filters.data_fim,
	}

	if filters.excluir_apuramento:
		# Só o apuramento deste exercício: os dos exercícios anteriores têm de ficar,
		# senão os resultados transitados desaparecem do capital próprio.
		condicoes.append(
			"NOT (gle.voucher_type = 'Period Closing Voucher' AND gle.posting_date >= %(ano_inicio)s)"
		)

	if filters.centro_de_custo:
		lft, rgt = frappe.db.get_value("Cost Center", filters.centro_de_custo, ["lft", "rgt"])
		condicoes.append(
			"gle.cost_center IN (SELECT name FROM `tabCost Center` WHERE lft >= %(cc_lft)s AND rgt <= %(cc_rgt)s)"
		)
		params.update(cc_lft=lft, cc_rgt=rgt)

	livro = filters.finance_book or frappe.get_cached_value("Company", filters.empresa, "default_finance_book")
	if livro:
		condicoes.append("(gle.finance_book IS NULL OR gle.finance_book IN ('', %(finance_book)s))")
		params["finance_book"] = livro
	else:
		condicoes.append("(gle.finance_book IS NULL OR gle.finance_book = '')")

	return frappe.db.sql(
		f"""
		SELECT gle.account,
			SUM(CASE WHEN gle.posting_date < %(ano_inicio)s
				THEN gle.debit - gle.credit ELSE 0 END) AS anos_anteriores,
			SUM(CASE WHEN gle.posting_date >= %(ano_inicio)s AND gle.is_opening = 'Yes'
				THEN gle.debit - gle.credit ELSE 0 END) AS abertura,
			SUM(CASE WHEN gle.posting_date >= %(ano_inicio)s AND gle.posting_date < %(data_inicio)s
				AND gle.is_opening != 'Yes' THEN gle.debit ELSE 0 END) AS anterior_debito,
			SUM(CASE WHEN gle.posting_date >= %(ano_inicio)s AND gle.posting_date < %(data_inicio)s
				AND gle.is_opening != 'Yes' THEN gle.credit ELSE 0 END) AS anterior_credito,
			SUM(CASE WHEN gle.posting_date >= %(data_inicio)s AND gle.is_opening != 'Yes'
				THEN gle.debit ELSE 0 END) AS periodo_debito,
			SUM(CASE WHEN gle.posting_date >= %(data_inicio)s AND gle.is_opening != 'Yes'
				THEN gle.credit ELSE 0 END) AS periodo_credito
		FROM `tabGL Entry` gle
		WHERE {" AND ".join(condicoes)}
		GROUP BY gle.account
		""",
		params,
		as_dict=True,
	)


def calcular_saldos(contas, movimentos, precisao):
	"""Preenche os saldos de cada conta e soma-os nas contas agregadoras.
	Devolve o resultado de exercícios anteriores que ficou por apurar."""
	for c in contas.values():
		c.saldo_inicial = c.movimento_debito = c.movimento_credito = 0.0
		c.acumulado_debito = c.acumulado_credito = 0.0

	resultado_por_apurar = 0.0
	for m in movimentos:
		c = contas.get(m.account)
		if not c:
			continue

		abertura = flt(m.abertura)
		if c.report_type == "Balance Sheet":
			abertura += flt(m.anos_anteriores)
		else:
			resultado_por_apurar += flt(m.anos_anteriores)

		anterior_debito, anterior_credito = flt(m.anterior_debito), flt(m.anterior_credito)
		periodo_debito, periodo_credito = flt(m.periodo_debito), flt(m.periodo_credito)

		c.saldo_inicial += abertura + anterior_debito - anterior_credito
		c.movimento_debito += periodo_debito
		c.movimento_credito += periodo_credito
		c.acumulado_debito += max(abertura, 0) + anterior_debito + periodo_debito
		c.acumulado_credito += max(-abertura, 0) + anterior_credito + periodo_credito

	# Ordem inversa da árvore: cada filha já está completa quando é somada à mãe.
	for c in reversed(list(contas.values())):
		if c.parent_account:
			pai = contas[c.parent_account]
			for campo in ("saldo_inicial", "movimento_debito", "movimento_credito", "acumulado_debito", "acumulado_credito"):
				pai[campo] += c[campo]

	for c in contas.values():
		saldo_final = flt(c.saldo_inicial + c.movimento_debito - c.movimento_credito, precisao)
		saldo_inicial = flt(c.saldo_inicial, precisao)
		c.saldo_inicial_debito = max(saldo_inicial, 0)
		c.saldo_inicial_credito = max(-saldo_inicial, 0)
		c.saldo_devedor = max(saldo_final, 0)
		c.saldo_credor = max(-saldo_final, 0)
		for campo in ("movimento_debito", "movimento_credito", "acumulado_debito", "acumulado_credito"):
			c[campo] = flt(c[campo], precisao)

	return flt(resultado_por_apurar, precisao)


def montar_linhas(contas, filters, moeda, precisao):
	tipo = filters.tipo or "Analítico"
	nivel_maximo = int(filters.nivel or 0)
	so_movimento = tipo == "Movimento"

	totais = frappe._dict({campo: 0.0 for campo in CAMPOS_VALOR})
	data = []
	for c in contas.values():
		if not c.parent_account:
			for campo in CAMPOS_VALOR:
				totais[campo] += c[campo]

		if tipo == "Sintético" and not c.is_group:
			continue
		if so_movimento and c.is_group:
			continue
		if nivel_maximo and c.nivel + 1 > nivel_maximo:
			continue
		if not filters.mostrar_sem_movimento and not any(c[campo] for campo in CAMPOS_VALOR):
			continue

		linha = {
			"account": c.name,
			# Na vista só de contas de movimento as mães não aparecem: lista plana.
			"parent_account": None if so_movimento else c.parent_account,
			"indent": 0 if so_movimento else c.nivel,
			"is_group": c.is_group,
			"conta": c.account_number or "",
			"designacao": c.account_name,
			"currency": moeda,
		}
		linha.update({campo: c[campo] for campo in CAMPOS_VALOR})
		data.append(linha)

	for campo in CAMPOS_VALOR:
		totais[campo] = flt(totais[campo], precisao)

	linha_total = {
		"account": None,
		"parent_account": None,
		"indent": 0,
		"is_total": 1,
		"conta": "",
		"designacao": _("Total"),
		"currency": moeda,
	}
	linha_total.update(totais)
	data.append(linha_total)
	return data, totais


def get_report_summary(totais, moeda):
	diferenca = flt(totais.saldo_devedor - totais.saldo_credor, 2)
	return [
		{
			"value": totais.saldo_devedor,
			"label": _("Total Saldos Devedores"),
			"datatype": "Currency",
			"currency": moeda,
		},
		{
			"value": totais.saldo_credor,
			"label": _("Total Saldos Credores"),
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
