"""Funcionalidades que cada cliente pode ligar ou desligar em Facturação Settings.

Os relatórios não dependem disto: estão sempre disponíveis.
"""

import json
import os

import frappe
from frappe import _
from frappe.utils import cint

SETTINGS = "Facturacao Settings"
# Workspaces da app: nome -> pasta em entre_facturacao/workspace.
WORKSPACES = {"Entre Facturacao": "entre_facturacao", "Facturacao": "facturacao"}

# fieldname em Facturação Settings -> nome mostrado nas mensagens.
FEATURES = {
	"feature_monitor_facturas": "Monitor de Facturas",
	"feature_agenda_factura": "Agenda de Factura",
	"feature_pagamento_rapido": "Pagamento Rápido",
	"feature_periodo_facturacao": "Período de Facturação",
	"feature_repeticao_automatica": "Ferramentas de Repetição Automática",
	"feature_centro_fiscal": "Centro Fiscal e Apuramento de IVA",
}

# O que cada funcionalidade tem no workspace (link_to dos links e atalhos).
WORKSPACE_ITEMS = {
	"feature_monitor_facturas": {"monitor-facturas"},
	"feature_agenda_factura": {"Agenda de Factura"},
	"feature_centro_fiscal": {"centro-fiscal", "Apuramento de IVA"},
}


def get_enabled():
	"""{fieldname: bool} de todas as funcionalidades."""
	settings = frappe.get_cached_doc(SETTINGS)
	return {f: bool(cint(settings.get(f))) for f in FEATURES}


def is_enabled(feature):
	return bool(cint(frappe.get_cached_doc(SETTINGS).get(feature)))


def check(feature):
	"""Para métodos chamados do browser: falha se a funcionalidade estiver desligada."""
	if not is_enabled(feature):
		frappe.throw(
			_("A funcionalidade {0} está desligada em Facturação Settings.").format(_(FEATURES[feature])),
			title=_("Funcionalidade desligada"),
		)


def set_defaults():
	"""Funcionalidades novas ficam ligadas, para que uma instalação que já as
	usava não as perca ao actualizar. Só escreve as que ainda não têm valor."""
	stored = set(frappe.db.sql_list("select field from `tabSingles` where doctype = %s", SETTINGS))
	missing = [f for f in FEATURES if f not in stored]
	for f in missing:
		frappe.db.set_single_value(SETTINGS, f, 1)
	if missing:
		frappe.clear_document_cache(SETTINGS, SETTINGS)


def sync_workspace():
	"""Reconstrói os workspaces a partir do JSON da app, sem os itens das
	funcionalidades desligadas. Corre ao gravar Facturação Settings e depois
	de cada migrate (que repõe o JSON)."""
	enabled = get_enabled()
	hidden = set()
	for feature, items in WORKSPACE_ITEMS.items():
		if not enabled.get(feature):
			hidden |= items

	for name, folder in WORKSPACES.items():
		if frappe.db.exists("Workspace", name):
			_sync_one(name, folder, hidden)


def _sync_one(name, folder, hidden):
	path = os.path.join(frappe.get_app_path("entre_facturacao"), "entre_facturacao", "workspace", folder, f"{folder}.json")
	with open(path, encoding="utf-8") as f:
		source = json.load(f)

	links = []
	card = None
	for l in source.get("links", []):
		l = dict(l)
		if l.get("type") == "Card Break":
			card = l
			card["link_count"] = 0
		elif l.get("link_to") in hidden:
			continue
		elif card:
			card["link_count"] += 1
		links.append(l)

	shortcuts = [dict(s) for s in source.get("shortcuts", []) if s.get("link_to") not in hidden]
	shortcut_labels = {s.get("label") for s in shortcuts}
	content = [
		block
		for block in json.loads(source.get("content") or "[]")
		if block.get("type") != "shortcut" or block.get("data", {}).get("shortcut_name") in shortcut_labels
	]

	# Sem ws.save(): em developer_mode o Workspace exportava-se por cima do
	# JSON da app, que tem de continuar a ter todos os itens.
	ws = frappe.get_doc("Workspace", name)
	ws.set("links", links)
	ws.set("shortcuts", shortcuts)
	ws.update_children()
	frappe.db.set_value("Workspace", name, "content", json.dumps(content), update_modified=False)
	frappe.clear_document_cache("Workspace", name)
