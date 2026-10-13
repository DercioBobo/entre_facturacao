"""Centro Fiscal: o estado das obrigações legais de uma empresa num mês.

Não tem lógica própria de cálculo: corre os relatórios (Balancete, Balanço,
Demonstração de Resultados) e o Apuramento de IVA com os filtros do mês e
resume o resultado, para que a página mostre exactamente o mesmo que eles."""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, get_first_day, get_last_day, getdate, today

from entre_facturacao import iva_modelo_a
from entre_facturacao.entre_facturacao.doctype.apuramento_de_iva.apuramento_de_iva import MESES
from entre_facturacao.entre_facturacao.report.balancete import balancete
from entre_facturacao.entre_facturacao.report.balanco import balanco
from entre_facturacao.entre_facturacao.report.demonstracao_de_resultados import demonstracao_de_resultados


@frappe.whitelist()
def get_estado(empresa, ano, mes):
	ano, mes = cint(ano), cint(mes)
	inicio = get_first_day(f"{ano}-{mes:02d}-01")
	fim = get_last_day(inicio)

	from erpnext.accounts.utils import get_fiscal_year

	try:
		ano_fiscal, ano_inicio, _fim = get_fiscal_year(fim, company=empresa)
	except Exception:
		ano_fiscal = ano_inicio = None

	periodo = frappe._dict(empresa=empresa, inicio=inicio, fim=fim, ano_fiscal=ano_fiscal, ano_inicio=ano_inicio)
	moeda = frappe.get_cached_value("Company", empresa, "default_currency")
	return {
		"moeda": moeda,
		"ano_fiscal": ano_fiscal,
		"ano_inicio": ano_inicio,
		"inicio": inicio,
		"fim": fim,
		"configuracao": seguro(configuracao, empresa),
		"iva": seguro(estado_iva, empresa, ano, mes),
		"historico_iva": seguro(historico_iva, empresa, ano),
		"balancete": seguro(estado_balancete, periodo) if ano_fiscal else sem_ano_fiscal(fim),
		"balanco": seguro(estado_balanco, periodo) if ano_fiscal else sem_ano_fiscal(fim),
		"demonstracao": seguro(estado_demonstracao, periodo) if ano_fiscal else sem_ano_fiscal(fim),
	}


def seguro(funcao, *args):
	"""Um cartão com erro não deve impedir a página de mostrar os outros."""
	try:
		return funcao(*args)
	except frappe.ValidationError as e:
		return {"erro": str(e)}
	except Exception:
		frappe.log_error(title=f"Centro Fiscal: {funcao.__name__}")
		return {"erro": _("Erro ao calcular. Ver Error Log.")}


def sem_ano_fiscal(data):
	return {"erro": _("Não há ano fiscal para {0}.").format(frappe.format_value(data, "Date"))}


def configuracao(empresa):
	"""Avisos de configuração que não dependem do período."""
	avisos = []
	cfg = iva_modelo_a.get_configuracao()
	contas = iva_modelo_a.contas_de_iva(empresa, cfg)
	if not (contas.liquidado or contas.dedutivel):
		avisos.append({"texto": _("As contas de IVA não estão configuradas."), "destino": "settings"})
	por_mapear = sorted(
		iva_modelo_a.usadas_em("Sales Taxes and Charges", contas.por_mapear)
		| iva_modelo_a.usadas_em("Purchase Taxes and Charges", contas.por_mapear)
	)
	if por_mapear:
		avisos.append(
			{
				"texto": _("Contas de impostos em uso que não estão nas Contas de IVA: {0}.").format(", ".join(por_mapear)),
				"destino": "settings",
			}
		)
	if not frappe.get_cached_value("Company", empresa, "tax_id"):
		avisos.append({"texto": _("A empresa não tem NUIT (Tax ID)."), "destino": "company"})
	return {"avisos": avisos}


def estado_iva(empresa, ano, mes):
	nome_mes = MESES[mes - 1]
	doc = frappe.db.get_value(
		"Apuramento de IVA",
		{"company": empresa, "ano": ano, "mes": nome_mes, "docstatus": ["<", 2]},
		["name", "docstatus", "campo_20", "campo_21", "campo_22", "prazo_entrega", "entrega", "avisos", "inexistencia_operacoes"],
		as_dict=True,
	)
	if doc:
		estado = "Submetido" if doc.docstatus == 1 else "Rascunho"
		avisos = [a for a in (doc.avisos or "").split("\n") if a]
	else:
		# Ainda não existe: estimativa com o mesmo cálculo, sem gravar nada.
		estado = "Por criar"
		doc = frappe.new_doc("Apuramento de IVA")
		doc.update({"company": empresa, "ano": ano, "mes": nome_mes, "data_entrega": today()})
		doc.definir_periodo()
		doc.preencher_do_anterior()
		doc.calcular()
		avisos = [a for a in (doc.avisos or "").split("\n") if a]
		doc = frappe._dict(doc.as_dict())
		doc.name = None

	prazo = getdate(doc.prazo_entrega)
	return {
		"estado": estado,
		"nome": doc.name,
		"nome_mes": nome_mes,
		"a_pagar": flt(doc.campo_20),
		"credito": flt(doc.campo_21),
		"reporte": flt(doc.campo_22),
		"sem_operacoes": cint(doc.inexistencia_operacoes),
		"prazo": prazo,
		"dias_para_prazo": date_diff(prazo, today()),
		"avisos": avisos,
	}


def historico_iva(empresa, ano):
	docs = {
		d.mes: d
		for d in frappe.get_all(
			"Apuramento de IVA",
			filters={"company": empresa, "ano": ano, "docstatus": ["<", 2]},
			fields=["name", "mes", "docstatus", "campo_20", "campo_21"],
		)
	}
	hoje = getdate(today())
	meses = []
	for n, nome in enumerate(MESES, start=1):
		d = docs.get(nome)
		inicio = getdate(f"{ano}-{n:02d}-01")
		if d:
			estado = "Submetido" if d.docstatus == 1 else "Rascunho"
		elif get_last_day(inicio) >= hoje:
			estado = "Futuro"
		else:
			estado = "Em falta"
		meses.append({"mes": n, "nome_mes": nome, "estado": estado, "nome": d.name if d else None})
	return {"meses": meses}


def correr(modulo, filtros):
	resultado = modulo.execute(frappe._dict(filtros))
	colunas, data = resultado[0], resultado[1]
	mensagem = resultado[2] if len(resultado) > 2 else None
	resumo = resultado[4] if len(resultado) > 4 else None
	return data, mensagem, resumo


def valor_do_resumo(resumo, label):
	return next((flt(c["value"]) for c in resumo or [] if c["label"] == label), 0.0)


def estado_balancete(p):
	filtros = {"empresa": p.empresa, "ano_fiscal": p.ano_fiscal, "data_inicio": p.inicio, "data_fim": p.fim}
	data, mensagem, resumo = correr(balancete, filtros)
	return {
		"filtros": filtros,
		"devedor": valor_do_resumo(resumo, _("Total Saldos Devedores")),
		"credor": valor_do_resumo(resumo, _("Total Saldos Credores")),
		"diferenca": valor_do_resumo(resumo, _("Diferença")),
		"avisos": [mensagem] if mensagem else [],
	}


def estado_balanco(p):
	filtros = {"empresa": p.empresa, "ano_fiscal": p.ano_fiscal, "data_fim": p.fim, "comparativo": 0}
	data, mensagem, resumo = correr(balanco, filtros)
	return {
		"filtros": {**filtros, "comparativo": 1},
		"activo": valor_do_resumo(resumo, _("Total dos Activos")),
		"diferenca": valor_do_resumo(resumo, _("Diferença")),
		"nao_mapeadas": sum(1 for r in data if (r.get("parent_linha") or "").startswith("__nao_mapeadas")),
		"avisos": mensagem.split("<br>") if mensagem else [],
	}


def estado_demonstracao(p):
	filtros = {
		"empresa": p.empresa,
		"ano_fiscal": p.ano_fiscal,
		"data_inicio": p.ano_inicio,
		"data_fim": p.fim,
		"comparativo": 0,
	}
	data, mensagem, resumo = correr(demonstracao_de_resultados, filtros)
	return {
		"filtros": {**filtros, "comparativo": 1},
		"resultado": valor_do_resumo(resumo, _("Resultado Líquido (Período n)")),
		"nao_mapeadas": sum(1 for r in data if r.get("parent_linha") == demonstracao_de_resultados.LINHA_NAO_MAPEADA),
		"avisos": [mensagem] if mensagem else [],
	}
