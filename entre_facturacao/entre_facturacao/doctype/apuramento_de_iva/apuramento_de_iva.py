"""Apuramento de IVA: um documento por empresa e mês, com os campos da
Declaração Periódica Modelo A (art. 36.º do CIVA).

Enquanto está em rascunho, cada gravação recalcula os campos 01 a 10 a partir
das facturas e da contabilidade (entre_facturacao.iva_modelo_a) e soma os
ajustes manuais. Ao submeter recalcula uma última vez e os valores ficam
fixos; o campo 22 passa a ser o campo 16 do mês seguinte.

Campos 11 a 23, conforme as instruções de preenchimento:
  11 = 01 + 03 + 04        12 = 05 + 06 + 07 + 08 + 09        13 = 02 + 10
  14 = 13 - 12 (se > 0)    15 = 12 - 13 (se > 0)
  16, 17 só se a declaração for entregue dentro do prazo
  18 = 14 - 16 - 17 (se > 0)    20 = 18 + 19
  21 = 15 + 16 + 17 - 14 (se > 0)    22 = 21 - 23
Todos os valores são arredondados por excesso para meticais."""

import math

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate

from entre_facturacao import iva_modelo_a

MESES = [
	"Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
	"Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
CAMPOS_APURADOS = ("01", "02", "03", "04", "05", "06", "07", "08", "09", "10")


def arredondar(valor):
	"""Por excesso para o metical (o valor absoluto, mantendo o sinal)."""
	valor = flt(valor, 2)
	if not valor:
		return 0
	return math.copysign(math.ceil(abs(valor) - 1e-9), valor)


class ApuramentodeIVA(Document):
	def autoname(self):
		abbr = frappe.get_cached_value("Company", self.company, "abbr")
		self.name = f"IVA-{abbr}-{self.ano}-{self.numero_mes():02d}"

	def numero_mes(self):
		return MESES.index(self.mes) + 1

	def validate(self):
		self.definir_periodo()
		self.validar_duplicado()
		self.preencher_identificacao()
		if self.is_new() and not self.amended_from:
			self.preencher_do_anterior()
		self.calcular()

	def definir_periodo(self):
		if not self.ano or self.ano < 2000:
			frappe.throw(_("Indique um ano válido."))
		self.data_inicio = get_first_day(f"{self.ano}-{self.numero_mes():02d}-01")
		self.data_fim = get_last_day(self.data_inicio)
		self.prazo_entrega = get_last_day(add_months(self.data_inicio, 1))
		self.entrega = (
			"Dentro do Prazo" if getdate(self.data_entrega or frappe.utils.today()) <= getdate(self.prazo_entrega) else "Fora do Prazo"
		)

	def validar_duplicado(self):
		outro = frappe.db.get_value(
			"Apuramento de IVA",
			{
				"company": self.company,
				"ano": self.ano,
				"mes": self.mes,
				"docstatus": ["<", 2],
				"name": ["!=", self.name or ""],
			},
		)
		if outro:
			frappe.throw(
				_("Já existe o apuramento {0} para {1} {2}. Cancele-o e use Corrigir (Amend) para o substituir.").format(
					frappe.bold(outro), self.mes, self.ano
				)
			)

	def preencher_identificacao(self):
		self.nuit = frappe.get_cached_value("Company", self.company, "tax_id")
		self.telefone = frappe.get_cached_value("Company", self.company, "phone_no")
		from frappe.contacts.doctype.address.address import get_company_address

		self.morada = (get_company_address(self.company) or {}).get("company_address_display")

	def preencher_do_anterior(self):
		data_anterior = add_months(get_first_day(f"{self.ano}-{self.numero_mes():02d}-01"), -1)
		anterior = frappe.db.get_value(
			"Apuramento de IVA",
			{
				"company": self.company,
				"ano": data_anterior.year,
				"mes": MESES[data_anterior.month - 1],
				"docstatus": 1,
			},
			["name", "campo_22", "cae"],
			as_dict=True,
		)
		if not anterior:
			return
		self.apuramento_anterior = anterior.name
		if not self.campo_16:
			self.campo_16 = anterior.campo_22
		if not self.cae:
			self.cae = anterior.cae

	def calcular(self):
		r = iva_modelo_a.calcular(self.company, self.data_inicio, self.data_fim, self.lancamento_apuramento)
		avisos = list(r.avisos)

		ajustes = {c: 0.0 for c in CAMPOS_APURADOS}
		for a in self.ajustes:
			ajustes[a.campo] += flt(a.valor)

		c = {}
		for campo in CAMPOS_APURADOS:
			c[campo] = arredondar(r.campos[campo] + ajustes[campo])
			if c[campo] < 0:
				avisos.append(
					_("O campo {0} ficou negativo ({1}). Reveja as notas de crédito ou os ajustes.").format(campo, c[campo])
				)

		c["11"] = c["01"] + c["03"] + c["04"]
		c["12"] = c["05"] + c["06"] + c["07"] + c["08"] + c["09"]
		c["13"] = c["02"] + c["10"]
		c["14"] = max(c["13"] - c["12"], 0)
		c["15"] = max(c["12"] - c["13"], 0)

		if self.entrega == "Fora do Prazo" and (flt(self.campo_16) or flt(self.campo_17)):
			avisos.append(_("Entrega fora do prazo: os créditos dos campos 16 e 17 não podem ser usados nesta declaração."))
			self.campo_16 = self.campo_17 = 0
		c["16"] = arredondar(self.campo_16)
		c["17"] = arredondar(self.campo_17)
		c["19"] = arredondar(self.campo_19)

		c["18"] = max(c["14"] - c["16"] - c["17"], 0)
		c["20"] = c["18"] + c["19"]
		c["21"] = max(c["15"] + c["16"] + c["17"] - c["14"], 0)

		c["23"] = arredondar(self.campo_23)
		if c["23"] > c["21"]:
			frappe.throw(_("O pedido de reembolso (campo 23) não pode ser maior que o crédito de imposto (campo 21)."))
		c["22"] = c["21"] - c["23"]

		for campo, valor in c.items():
			self.set(f"campo_{campo}", valor)

		self.set("documentos", [])
		for d in r.documentos:
			self.append("documentos", d)
		self.set("reconciliacao", [])
		for linha in r.reconciliacao:
			self.append("reconciliacao", linha)
			if abs(linha["diferenca"]) >= 0.5:
				avisos.append(
					_("A conta {0} tem {1} de movimentos que não vêm de facturas (ver Reconciliação com a Contabilidade).").format(
						linha["conta"], frappe.format_value(linha["diferenca"], {"fieldtype": "Currency"})
					)
				)

		self.inexistencia_operacoes = int(not r.documentos and not any(c[x] for x in CAMPOS_APURADOS))
		self.avisos = "\n".join(avisos)
