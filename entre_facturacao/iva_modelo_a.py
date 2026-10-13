"""Apuramento do IVA para a Declaração Periódica Modelo A (art. 36.º do CIVA).

Classifica os documentos do período nos campos 01 a 10 do Quadro 05:

- Facturas de venda (Sales Invoice): a base de cada linha vai para 01, 03 ou 04
  e o IVA das contas "IVA Liquidado" vai para 02. A linha vai para:
    1. o campo marcado no Item Tax Template da linha, se houver;
    2. 01, se a linha paga IVA (taxa na conta de IVA liquidado > 0);
    3. o campo marcado no Sales Taxes and Charges Template da factura (ex.:
       exportações -> 03);
    4. senão fica "NC" (não classificada) e é assinalada.
- Facturas de compra (Purchase Invoice): o IVA das contas "IVA Dedutível" é
  repartido pelas linhas (na proporção base x taxa) e vai para 05 se o artigo é
  imobilizado, 06 se é de stock (existências) ou 07 nos restantes casos.
- Contas "IVA Dedutível - Importações": o movimento a débito no período
  (qualquer documento, normalmente o Documento Único) vai para 08.
- Contas "IVA Regularizações": débitos vão para 09 (a favor do sujeito
  passivo), créditos para 10 (a favor do Estado).
- Notas de crédito: conforme Facturação Settings, ou entram como regularização
  (vendas -> 09, compras -> 10) ou são abatidas nos campos de origem.

Valores em moeda da empresa (campos base_*). O arredondamento por excesso para
meticais e os campos 11 a 23 são feitos no documento Apuramento de IVA."""

import json
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

LIQUIDADO = "IVA Liquidado"
DEDUTIVEL = "IVA Dedutível"
IMPORTACOES = "IVA Dedutível - Importações"
REGULARIZACOES = "IVA Regularizações"

NOTAS_CREDITO_REGULARIZACAO = "Regularização (campos 09 e 10)"

CAMPOS_BASE = ("01", "03", "04", "05", "06", "07", "08", "09", "10")
CAMPOS = ("01", "02") + CAMPOS_BASE[1:]

DESCRICAO_CAMPO = {
	"01": _("Transmissões de bens e prestações de serviços tributadas (base tributável)"),
	"02": _("IVA liquidado"),
	"03": _("Isentas com direito a dedução (art. 18.º, n.º 1, al. b) do CIVA)"),
	"04": _("Isentas sem direito a dedução (art. 9.º do CIVA)"),
	"05": _("IVA dedutível: imobilizado"),
	"06": _("IVA dedutível: existências"),
	"07": _("IVA dedutível: outros bens e serviços"),
	"08": _("IVA dedutível nas importações"),
	"09": _("Regularizações a favor do sujeito passivo"),
	"10": _("Regularizações a favor do Estado"),
	"NC": _("Não classificado"),
}


def campo_da_opcao(valor):
	"""'03 - Isenta com direito a dedução' -> '03'."""
	return (valor or "")[:2] or None


def calcular(empresa, data_inicio, data_fim, excluir_voucher=None):
	contas = {
		c.name: c.iva_modelo_a
		for c in frappe.get_all(
			"Account",
			filters={"company": empresa, "iva_modelo_a": ["is", "set"]},
			fields=["name", "iva_modelo_a"],
		)
	}
	notas_credito_regularizacao = (
		frappe.db.get_single_value("Facturacao Settings", "iva_notas_credito") or NOTAS_CREDITO_REGULARIZACAO
	) == NOTAS_CREDITO_REGULARIZACAO

	r = frappe._dict(campos=defaultdict(float), documentos={}, avisos=[], por_conta=defaultdict(float))
	if not contas:
		r.avisos.append(
			_("Nenhuma conta está marcada com o campo \"IVA (Modelo A)\" no plano de contas de {0}.").format(empresa)
		)

	vendas(r, contas, empresa, data_inicio, data_fim, notas_credito_regularizacao)
	compras(r, contas, empresa, data_inicio, data_fim, notas_credito_regularizacao)
	movimentos_contabilisticos(r, contas, empresa, data_inicio, data_fim)

	nao_classificadas = [d for d in r.documentos.values() if d["campo"] == "NC"]
	if nao_classificadas:
		r.avisos.append(
			_("{0} documento(s) com linhas sem IVA e sem classificação (campo \"NC\"). Marque o Item Tax Template ou o "
			"Sales Taxes and Charges Template como 03 ou 04: {1}").format(
				len(nao_classificadas), ", ".join(d["documento"] for d in nao_classificadas[:10])
			)
		)

	return frappe._dict(
		campos={c: flt(r.campos.get(c), 2) for c in CAMPOS},
		documentos=sorted(r.documentos.values(), key=lambda d: (d["campo"], str(d["data"]), d["documento"])),
		reconciliacao=reconciliacao(r, contas, empresa, data_inicio, data_fim, excluir_voucher),
		avisos=r.avisos,
	)


def adicionar(r, campo, doc, tipo_documento, base=0.0, iva=0.0, entidade=None, nuit=None, referencia=None):
	if campo != "NC":
		if campo == "01":
			r.campos["01"] += base
			r.campos["02"] += iva
		elif campo in ("03", "04"):
			r.campos[campo] += base
		else:
			r.campos[campo] += iva
	chave = (tipo_documento, doc.name, campo)
	d = r.documentos.setdefault(
		chave,
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


def vendas(r, contas, empresa, data_inicio, data_fim, notas_credito_regularizacao):
	facturas = frappe.get_all(
		"Sales Invoice",
		filters={
			"company": empresa,
			"docstatus": 1,
			"is_opening": ["!=", "Yes"],
			"posting_date": ["between", [data_inicio, data_fim]],
		},
		fields=["name", "posting_date", "customer_name", "tax_id", "is_return", "taxes_and_charges"],
	)
	if not facturas:
		return
	nomes = [f.name for f in facturas]
	linhas = filhos("Sales Invoice Item", nomes, ["base_net_amount", "item_tax_template", "item_tax_rate"])
	impostos = filhos("Sales Taxes and Charges", nomes, ["account_head", "base_tax_amount_after_discount_amount"])
	campo_item_template = opcoes_por_template("Item Tax Template")
	campo_taxes_template = opcoes_por_template("Sales Taxes and Charges Template")
	liquidado = {c for c, t in contas.items() if t == LIQUIDADO}

	for f in facturas:
		iva = 0.0
		for t in impostos.get(f.name, []):
			if t.account_head in liquidado:
				valor = flt(t.base_tax_amount_after_discount_amount)
				iva += valor
				r.por_conta[t.account_head] += valor

		bases = defaultdict(float)
		for linha in linhas.get(f.name, []):
			taxas = taxas_da_linha(linha)
			taxa_iva = [flt(v) for k, v in taxas.items() if k in liquidado]
			paga_iva = sum(taxa_iva) > 0 if taxa_iva else bool(iva)
			campo = (
				campo_item_template.get(linha.item_tax_template)
				or ("01" if paga_iva else None)
				or campo_taxes_template.get(f.taxes_and_charges)
				or "NC"
			)
			bases[campo] += flt(linha.base_net_amount)
		if iva and "01" not in bases:
			bases["01"] += 0.0

		args = dict(entidade=f.customer_name, nuit=f.tax_id)
		if f.is_return and notas_credito_regularizacao:
			# Nota de crédito: IVA devolvido ao cliente regulariza a favor do sujeito passivo.
			if iva:
				adicionar(r, "09", f, "Sales Invoice", base=-sum(bases.values()), iva=-iva, **args)
			continue
		for campo, base in bases.items():
			adicionar(r, campo, f, "Sales Invoice", base=base, iva=iva if campo == "01" else 0.0, **args)


def compras(r, contas, empresa, data_inicio, data_fim, notas_credito_regularizacao):
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
		["account_head", "base_tax_amount_after_discount_amount", "add_deduct_tax", "rate"],
	)
	codigos = {l.item_code for ls in linhas.values() for l in ls if l.item_code}
	de_stock = set(
		frappe.get_all("Item", filters={"name": ["in", list(codigos)], "is_stock_item": 1}, pluck="name")
	) if codigos else set()
	dedutivel = {c for c, t in contas.items() if t == DEDUTIVEL}

	for f in facturas:
		por_campo = defaultdict(float)
		base_por_campo = defaultdict(float)
		linhas_f = linhas.get(f.name, [])
		for linha in linhas_f:
			base_por_campo[campo_da_compra(linha, de_stock)] += flt(linha.base_net_amount)

		for t in impostos.get(f.name, []):
			if t.account_head not in dedutivel:
				continue
			valor = flt(t.base_tax_amount_after_discount_amount)
			if t.add_deduct_tax == "Deduct":
				valor = -valor
			r.por_conta[t.account_head] += valor
			for campo, parte in repartir(valor, t, linhas_f, de_stock).items():
				por_campo[campo] += parte

		if not por_campo:
			continue
		args = dict(entidade=f.supplier_name, nuit=f.tax_id, referencia=f.bill_no)
		if f.is_return and notas_credito_regularizacao:
			# Nota de crédito do fornecedor: IVA a devolver regulariza a favor do Estado.
			adicionar(r, "10", f, "Purchase Invoice", base=-sum(base_por_campo.values()), iva=-sum(por_campo.values()), **args)
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
	gl = [c for c, t in contas.items() if t in (IMPORTACOES, REGULARIZACOES)]
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
		if contas[m.account] == IMPORTACOES:
			if liquido:
				adicionar(r, "08", doc, m.voucher_type, iva=liquido)
		else:
			if liquido > 0:
				adicionar(r, "09", doc, m.voucher_type, iva=liquido)
			elif liquido < 0:
				adicionar(r, "10", doc, m.voucher_type, iva=-liquido)


def reconciliacao(r, contas, empresa, data_inicio, data_fim, excluir_voucher):
	"""Compara, por conta de IVA liquidado/dedutível, o movimento na
	contabilidade com o que foi apurado a partir das facturas."""
	alvo = [c for c, t in contas.items() if t in (LIQUIDADO, DEDUTIVEL)]
	if not alvo:
		return []
	movimento = {
		row.account: row
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
	for conta in sorted(alvo):
		m = movimento.get(conta)
		debito, credito = (flt(m.debit), flt(m.credit)) if m else (0.0, 0.0)
		contabilidade = credito - debito if contas[conta] == LIQUIDADO else debito - credito
		documentos = flt(r.por_conta.get(conta), 2)
		contabilidade = flt(contabilidade, 2)
		if not (contabilidade or documentos):
			continue
		linhas.append(
			{
				"conta": conta,
				"tipo": contas[conta],
				"contabilidade": contabilidade,
				"documentos": documentos,
				"diferenca": flt(contabilidade - documentos, 2),
			}
		)
	return linhas


def opcoes_por_template(doctype):
	return {
		t.name: campo_da_opcao(t.iva_campo_modelo_a)
		for t in frappe.get_all(doctype, filters={"iva_campo_modelo_a": ["is", "set"]}, fields=["name", "iva_campo_modelo_a"])
	}
