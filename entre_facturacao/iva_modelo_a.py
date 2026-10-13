"""Apuramento do IVA para a Declaração Periódica Modelo A (art. 36.º do CIVA).

A configuração está em Facturação Settings > Apuramento de IVA:
- "Contas de IVA" (IVA Conta): que contas são IVA liquidado, dedutível,
  das importações, de regularizações, ou "Não é IVA".
- "Modelos de Impostos" (IVA Modelo): para que campo (01/03/04) vão as vendas
  com cada Item Tax Template ou Sales Taxes and Charges Template.
O botão "Detectar Configuração de IVA" preenche as duas tabelas a partir da
configuração do ERPNext (detectar()); o apuramento usa só as tabelas e avisa
quando aparece no período uma conta de impostos ou um modelo que não está lá.

Vendas (Sales Invoice): a base de cada linha vai para
    1. o campo do Item Tax Template da linha, se estiver na tabela;
    2. 01, se a linha paga IVA;
    3. o campo do Sales Taxes and Charges Template da factura, se estiver na tabela;
    4. 03 se o cliente é do estrangeiro e a opção de exportações está activa
       (país da morada da factura diferente do da empresa), senão 04.
  O IVA das contas de IVA liquidado vai para 02.
Compras (Purchase Invoice): o IVA das contas de IVA dedutível é repartido pelas
  linhas na proporção base x taxa: 05 imobilizado, 06 artigos de stock, 07 o
  resto. Linhas de impostos "Valuation and Total" (IVA não dedutível, que vai
  ao custo) ficam de fora, se a opção estiver activa.
Contas de importações: o movimento a débito do período vai para 08.
Contas de regularizações: débitos para 09, créditos para 10.
Notas de crédito: como regularização (vendas 09, compras 10) ou abatidas nos
  campos de origem, conforme a opção.

Valores em moeda da empresa (campos base_*). O arredondamento por excesso para
meticais e os campos 11 a 23 são feitos no documento Apuramento de IVA."""

import json
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

LIQUIDADO = "IVA Liquidado"
DEDUTIVEL = "IVA Dedutível"
AMBOS = "IVA Liquidado e Dedutível"
IMPORTACOES = "IVA Dedutível - Importações"
REGULARIZACOES = "IVA Regularizações"
NAO_E_IVA = "Não é IVA"

NOTAS_CREDITO_REGULARIZACAO = "Regularização (campos 09 e 10)"

ITEM_TAX_TEMPLATE = "Item Tax Template"
SALES_TAXES_TEMPLATE = "Sales Taxes and Charges Template"
CAMPO_ISENTA_SEM_DEDUCAO = "04 - Isenta sem direito a dedução"
CAMPO_ISENTA_COM_DEDUCAO = "03 - Isenta com direito a dedução"

CAMPOS = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")

# Nome de conta que indica IVA (para a detecção sugerir "Não é IVA" às outras).
PARECE_IVA = re.compile(r"\b(iva|vat)\b|valor acrescentado", re.IGNORECASE)


def campo_da_opcao(valor):
	"""'03 - Isenta com direito a dedução' -> '03'."""
	return (valor or "")[:2] or None


def get_configuracao():
	settings = frappe.get_cached_doc("Facturacao Settings")
	return frappe._dict(
		notas_credito_regularizacao=(settings.iva_notas_credito or NOTAS_CREDITO_REGULARIZACAO) == NOTAS_CREDITO_REGULARIZACAO,
		exportacao=cint(settings.iva_exportacao),
		excluir_nao_dedutivel=cint(settings.iva_excluir_nao_dedutivel),
		contas={c.conta: c.tipo for c in settings.iva_contas},
		modelos={(m.tipo_modelo, m.modelo): campo_da_opcao(m.campo) for m in settings.iva_modelos},
	)


def calcular(empresa, data_inicio, data_fim, excluir_voucher=None):
	cfg = get_configuracao()
	contas = contas_de_iva(empresa, cfg)

	# por_conta: IVA apurado nas facturas, no sentido do crédito (vendas +, compras -).
	r = frappe._dict(
		campos=defaultdict(float),
		documentos={},
		avisos=[],
		por_conta=defaultdict(float),
		contas_por_mapear=set(),
		modelos_por_mapear=set(),
	)
	if not (contas.liquidado or contas.dedutivel):
		r.avisos.append(
			_("Não há contas de IVA liquidado ou dedutível de {0} em Facturação Settings > Contas de IVA. "
			"Use \"Detectar Configuração de IVA\".").format(empresa)
		)

	vendas(r, contas, cfg, empresa, data_inicio, data_fim)
	compras(r, contas, cfg, empresa, data_inicio, data_fim)
	movimentos_contabilisticos(r, contas, empresa, data_inicio, data_fim)

	if r.contas_por_mapear:
		r.avisos.append(
			_("Contas de impostos usadas no período que não estão em Facturação Settings > Contas de IVA (não foram "
			"consideradas): {0}. Use \"Detectar Configuração de IVA\" ou acrescente-as à tabela.").format(
				", ".join(sorted(r.contas_por_mapear))
			)
		)
	if r.modelos_por_mapear:
		r.avisos.append(
			_("Modelos de impostos com vendas sem IVA que não estão em Facturação Settings > Modelos de Impostos (foram "
			"para o campo 03/04 pela regra geral): {0}.").format(", ".join(sorted(r.modelos_por_mapear)))
		)

	return frappe._dict(
		campos={c: flt(r.campos.get(c), 2) for c in CAMPOS},
		documentos=sorted(r.documentos.values(), key=lambda d: (d["campo"], str(d["data"]), d["documento"])),
		reconciliacao=reconciliacao(r, contas, empresa, data_inicio, data_fim, excluir_voucher),
		avisos=r.avisos,
	)


def contas_de_impostos(empresa):
	"""Contas do tipo "Tax" da empresa, sem as de retenção na fonte."""
	impostos = set(frappe.get_all("Account", filters={"company": empresa, "account_type": "Tax", "is_group": 0}, pluck="name"))
	retencao = set(frappe.get_all("Tax Withholding Account", filters={"company": empresa}, pluck="account"))
	return impostos - retencao


def contas_de_iva(empresa, cfg):
	da_empresa = set(
		frappe.get_all("Account", filters={"company": empresa, "name": ["in", list(cfg.contas) or [""]]}, pluck="name")
	)
	c = frappe._dict(liquidado=set(), dedutivel=set(), importacoes=set(), regularizacoes=set())
	for conta, tipo in cfg.contas.items():
		if conta not in da_empresa:
			continue
		if tipo in (LIQUIDADO, AMBOS):
			c.liquidado.add(conta)
		if tipo in (DEDUTIVEL, AMBOS):
			c.dedutivel.add(conta)
		if tipo == IMPORTACOES:
			c.importacoes.add(conta)
		if tipo == REGULARIZACOES:
			c.regularizacoes.add(conta)
	c.por_mapear = contas_de_impostos(empresa) - da_empresa
	return c


def adicionar(r, campo, doc, tipo_documento, base=0.0, iva=0.0, entidade=None, nuit=None, referencia=None):
	if campo == "01":
		r.campos["01"] += base
		r.campos["02"] += iva
	elif campo in ("03", "04"):
		r.campos[campo] += base
	else:
		r.campos[campo] += iva
	d = r.documentos.setdefault(
		(tipo_documento, doc.name, campo),
		{
			"campo": campo,
			"tipo_documento": tipo_documento,
			"documento": doc.name,
			"data": doc.posting_date,
			"entidade": entidade,
			"nuit_entidade": nuit,
			"referencia": referencia,
			"base": 0.0,
			"iva": 0.0,
		},
	)
	d["base"] += base
	d["iva"] += iva


def filhos(doctype, pais, fields):
	por_pai = defaultdict(list)
	for lote in range(0, len(pais), 500):
		for row in frappe.get_all(
			doctype,
			filters={"parent": ["in", pais[lote : lote + 500]]},
			fields=["parent", *fields],
			order_by="idx",
		):
			por_pai[row.parent].append(row)
	return por_pai


def taxas_da_linha(linha):
	try:
		return json.loads(linha.item_tax_rate or "{}") or {}
	except ValueError:
		return {}


def paises_das_moradas(nomes):
	nomes = [n for n in set(nomes) if n]
	if not nomes:
		return {}
	return {a.name: a.country for a in frappe.get_all("Address", filters={"name": ["in", nomes]}, fields=["name", "country"])}


def vendas(r, contas, cfg, empresa, data_inicio, data_fim):
	facturas = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": empresa,
			"docstatus": 1,
			"is_opening": ["!=", "Yes"],
			"posting_date": ["between", [data_inicio, data_fim]],
		},
		fields=["name", "posting_date", "customer_name", "tax_id", "is_return", "taxes_and_charges", "customer_address"],
	)
	if not facturas:
		return
	nomes = [f.name for f in facturas]
	linhas = filhos("Sales Invoice Item", nomes, ["base_net_amount", "item_tax_template", "item_tax_rate"])
	impostos = filhos("Sales Taxes and Charges", nomes, ["account_head", "base_tax_amount_after_discount_amount"])
	pais_empresa = frappe.get_cached_value("Company", empresa, "country")
	paises = paises_das_moradas(f.customer_address for f in facturas) if cfg.exportacao else {}

	for f in facturas:
		iva = 0.0
		for t in impostos.get(f.name, []):
			if t.account_head in contas.liquidado:
				valor = flt(t.base_tax_amount_after_discount_amount)
				iva += valor
				r.por_conta[t.account_head] += valor
			elif t.account_head in contas.por_mapear:
				r.contas_por_mapear.add(t.account_head)

		pais_cliente = paises.get(f.customer_address)
		regra_geral = "03" if pais_cliente and pais_empresa and pais_cliente != pais_empresa else "04"

		bases = defaultdict(float)
		for linha in linhas.get(f.name, []):
			taxa_iva = [flt(v) for k, v in taxas_da_linha(linha).items() if k in contas.liquidado]
			paga_iva = sum(taxa_iva) > 0 if taxa_iva else bool(iva)
			campo = cfg.modelos.get((ITEM_TAX_TEMPLATE, linha.item_tax_template))
			if not campo and paga_iva:
				campo = "01"
			if not campo:
				campo = cfg.modelos.get((SALES_TAXES_TEMPLATE, f.taxes_and_charges))
			if not campo:
				campo = regra_geral
				for modelo in (linha.item_tax_template, f.taxes_and_charges):
					if modelo:
						r.modelos_por_mapear.add(modelo)
			bases[campo] += flt(linha.base_net_amount)
		if iva and "01" not in bases:
			bases["01"] += 0.0

		args = dict(entidade=f.customer_name, nuit=f.tax_id)
		if f.is_return and cfg.notas_credito_regularizacao:
			# Nota de crédito: o IVA devolvido ao cliente regulariza a favor do sujeito passivo.
			if iva:
				adicionar(r, "09", f, "Sales Invoice", base=-sum(bases.values()), iva=-iva, **args)
			continue
		for campo, base in bases.items():
			adicionar(r, campo, f, "Sales Invoice", base=base, iva=iva if campo == "01" else 0.0, **args)


def compras(r, contas, cfg, empresa, data_inicio, data_fim):
	facturas = frappe.get_all(
		"Purchase Invoice",
		filters={
			"company": empresa,
			"docstatus": 1,
			"is_opening": ["!=", "Yes"],
			"posting_date": ["between", [data_inicio, data_fim]],
		},
		fields=["name", "posting_date", "supplier_name", "tax_id", "is_return", "bill_no"],
	)
	if not facturas:
		return
	nomes = [f.name for f in facturas]
	linhas = filhos("Purchase Invoice Item", nomes, ["item_code", "base_net_amount", "is_fixed_asset", "item_tax_rate"])
	impostos = filhos(
		"Purchase Taxes and Charges",
		nomes,
		["account_head", "base_tax_amount_after_discount_amount", "add_deduct_tax", "category", "rate"],
	)
	codigos = {l.item_code for ls in linhas.values() for l in ls if l.item_code}
	de_stock = (
		set(frappe.get_all("Item", filters={"name": ["in", list(codigos)], "is_stock_item": 1}, pluck="name"))
		if codigos
		else set()
	)

	for f in facturas:
		por_campo = defaultdict(float)
		base_por_campo = defaultdict(float)
		linhas_f = linhas.get(f.name, [])
		for linha in linhas_f:
			base_por_campo[campo_da_compra(linha, de_stock)] += flt(linha.base_net_amount)

		for t in impostos.get(f.name, []):
			if t.account_head not in contas.dedutivel:
				if t.account_head in contas.por_mapear:
					r.contas_por_mapear.add(t.account_head)
				continue
			# "Valuation and Total": IVA não dedutível, incorporado no custo.
			if cfg.excluir_nao_dedutivel and t.category not in (None, "", "Total"):
				continue
			valor = flt(t.base_tax_amount_after_discount_amount)
			if t.add_deduct_tax == "Deduct":
				valor = -valor
			r.por_conta[t.account_head] -= valor
			for campo, parte in repartir(valor, t, linhas_f, de_stock).items():
				por_campo[campo] += parte

		if not por_campo:
			continue
		args = dict(entidade=f.supplier_name, nuit=f.tax_id, referencia=f.bill_no)
		if f.is_return and cfg.notas_credito_regularizacao:
			# Nota de crédito do fornecedor: o IVA a devolver regulariza a favor do Estado.
			adicionar(
				r, "10", f, "Purchase Invoice", base=-sum(base_por_campo.values()), iva=-sum(por_campo.values()), **args
			)
			continue
		for campo, iva in por_campo.items():
			adicionar(r, campo, f, "Purchase Invoice", base=base_por_campo.get(campo, 0.0), iva=iva, **args)


def campo_da_compra(linha, de_stock):
	if linha.is_fixed_asset:
		return "05"
	if linha.item_code in de_stock:
		return "06"
	return "07"


def repartir(valor, imposto, linhas, de_stock):
	"""Reparte o IVA de uma linha de impostos pelas linhas da factura, na
	proporção base x taxa da conta (a do item, se tiver Item Tax Template)."""
	pesos = defaultdict(float)
	for linha in linhas:
		taxas = taxas_da_linha(linha)
		taxa = flt(taxas[imposto.account_head]) if imposto.account_head in taxas else (flt(imposto.rate) or 1)
		pesos[campo_da_compra(linha, de_stock)] += flt(linha.base_net_amount) * taxa
	total = sum(pesos.values())
	if not total:
		return {"07": valor}
	return {campo: valor * peso / total for campo, peso in pesos.items() if peso}


def movimentos_contabilisticos(r, contas, empresa, data_inicio, data_fim):
	gl = list(contas.importacoes | contas.regularizacoes)
	if not gl:
		return
	movimentos = frappe.db.sql(
		"""
		SELECT gle.account, gle.voucher_type, gle.voucher_no, MIN(gle.posting_date) AS posting_date,
			SUM(gle.debit) AS debit, SUM(gle.credit) AS credit
		FROM `tabGL Entry` gle
		WHERE gle.company = %(empresa)s AND gle.is_cancelled = 0
			AND gle.voucher_type != 'Period Closing Voucher'
			AND gle.posting_date BETWEEN %(inicio)s AND %(fim)s
			AND gle.account IN %(contas)s
		GROUP BY gle.account, gle.voucher_type, gle.voucher_no
		""",
		{"empresa": empresa, "inicio": data_inicio, "fim": data_fim, "contas": gl},
		as_dict=True,
	)
	for m in movimentos:
		doc = frappe._dict(name=m.voucher_no, posting_date=m.posting_date)
		liquido = flt(m.debit) - flt(m.credit)
		if m.account in contas.importacoes:
			if liquido:
				adicionar(r, "08", doc, m.voucher_type, iva=liquido)
		elif liquido > 0:
			adicionar(r, "09", doc, m.voucher_type, iva=liquido)
		elif liquido < 0:
			adicionar(r, "10", doc, m.voucher_type, iva=-liquido)


def reconciliacao(r, contas, empresa, data_inicio, data_fim, excluir_voucher):
	"""Compara, por conta de IVA liquidado/dedutível, o movimento na
	contabilidade com o que foi apurado a partir das facturas. Mostra os valores
	no sentido natural da conta (crédito para o liquidado, débito para o
	dedutível; crédito - débito se a conta serve para os dois)."""
	alvo = sorted(contas.liquidado | contas.dedutivel)
	if not alvo:
		return []
	movimento = {
		row.account: flt(row.credit) - flt(row.debit)
		for row in frappe.db.sql(
			"""
			SELECT gle.account, SUM(gle.debit) AS debit, SUM(gle.credit) AS credit
			FROM `tabGL Entry` gle
			WHERE gle.company = %(empresa)s AND gle.is_cancelled = 0
				AND gle.voucher_type != 'Period Closing Voucher'
				AND gle.posting_date BETWEEN %(inicio)s AND %(fim)s
				AND gle.account IN %(contas)s
				AND gle.voucher_no != %(excluir)s
			GROUP BY gle.account
			""",
			{"empresa": empresa, "inicio": data_inicio, "fim": data_fim, "contas": alvo, "excluir": excluir_voucher or ""},
			as_dict=True,
		)
	}
	linhas = []
	for conta in alvo:
		liquidado, dedutivel = conta in contas.liquidado, conta in contas.dedutivel
		sinal = -1 if dedutivel and not liquidado else 1
		contabilidade = flt(sinal * movimento.get(conta, 0.0), 2)
		documentos = flt(sinal * r.por_conta.get(conta, 0.0), 2)
		if not (contabilidade or documentos):
			continue
		linhas.append(
			{
				"conta": conta,
				"tipo": AMBOS if liquidado and dedutivel else LIQUIDADO if liquidado else DEDUTIVEL,
				"contabilidade": contabilidade,
				"documentos": documentos,
				"diferenca": flt(contabilidade - documentos, 2),
			}
		)
	return linhas


@frappe.whitelist()
def detectar():
	"""Sugestão para as tabelas de Facturação Settings, a partir dos modelos de
	impostos e das facturas existentes, para todas as empresas. Não grava nada:
	o formulário junta as linhas novas às que já existem e o utilizador revê."""
	frappe.only_for(("Accounts Manager", "System Manager"))
	contas, modelos = [], []
	for empresa in frappe.get_all("Company", pluck="name"):
		candidatas = contas_de_impostos(empresa)
		if not candidatas:
			continue
		nomes = {
			a.name: a.account_name
			for a in frappe.get_all("Account", filters={"name": ["in", list(candidatas)]}, fields=["name", "account_name"])
		}
		vendas_ = usadas_em("Sales Taxes and Charges", candidatas)
		compras_ = usadas_em("Purchase Taxes and Charges", candidatas)

		liquidado = set()
		for conta in sorted(candidatas):
			nome = nomes.get(conta) or conta
			parece_iva = bool(PARECE_IVA.search(nome))
			if conta in vendas_ or conta in compras_:
				if not parece_iva:
					tipo = NAO_E_IVA
				elif conta in vendas_ and conta in compras_:
					tipo = AMBOS
				else:
					tipo = LIQUIDADO if conta in vendas_ else DEDUTIVEL
			elif parece_iva and re.search(r"import", nome, re.IGNORECASE):
				tipo = IMPORTACOES
			elif parece_iva and re.search(r"regulariz", nome, re.IGNORECASE):
				tipo = REGULARIZACOES
			else:
				continue
			if tipo in (LIQUIDADO, AMBOS):
				liquidado.add(conta)
			contas.append({"conta": conta, "empresa": empresa, "tipo": tipo})

		modelos += modelos_isentos(empresa, liquidado)
	return {"contas": contas, "modelos": modelos}


def usadas_em(doctype, contas):
	if not contas:
		return set()
	return {
		r[0]
		for r in frappe.db.sql(
			f"SELECT DISTINCT account_head FROM `tab{doctype}` WHERE account_head IN %(contas)s",
			{"contas": list(contas)},
		)
	}


def modelos_isentos(empresa, liquidado):
	"""Item Tax Templates com taxa 0 numa conta de IVA liquidado, e Sales Taxes
	and Charges Templates sem IVA: isentos (04, ou 03 se o nome indica exportação)."""
	if not liquidado:
		return []
	sugestoes = []

	def campo(nome):
		return CAMPO_ISENTA_COM_DEDUCAO if re.search(r"export", nome or "", re.IGNORECASE) else CAMPO_ISENTA_SEM_DEDUCAO

	itens = frappe.get_all("Item Tax Template", filters={"company": empresa, "disabled": 0}, pluck="name")
	taxas = filhos("Item Tax Template Detail", itens, ["tax_type", "tax_rate"]) if itens else {}
	for modelo in itens:
		linhas_iva = [t for t in taxas.get(modelo, []) if t.tax_type in liquidado]
		if linhas_iva and all(not flt(t.tax_rate) for t in linhas_iva):
			sugestoes.append({"tipo_modelo": ITEM_TAX_TEMPLATE, "modelo": modelo, "campo": campo(modelo)})

	vendas_ = frappe.get_all(SALES_TAXES_TEMPLATE, filters={"company": empresa, "disabled": 0}, pluck="name")
	linhas = filhos("Sales Taxes and Charges", vendas_, ["account_head", "rate"]) if vendas_ else {}
	for modelo in vendas_:
		if not any(t.account_head in liquidado and flt(t.rate) for t in linhas.get(modelo, [])):
			sugestoes.append({"tipo_modelo": SALES_TAXES_TEMPLATE, "modelo": modelo, "campo": campo(modelo)})
	return sugestoes
