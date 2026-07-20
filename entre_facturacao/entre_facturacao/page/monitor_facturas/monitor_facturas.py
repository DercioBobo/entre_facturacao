from html import escape as html_escape

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, now_datetime, today
from frappe.utils.pdf import get_pdf
from frappe.utils.xlsxutils import make_xlsx

FREQ_LABELS = {
	"Daily": "Diária",
	"Weekly": "Semanal",
	"Monthly": "Mensal",
	"Quarterly": "Trimestral",
	"Half-yearly": "Semestral",
	"Yearly": "Anual",
}


def _query_invoices(from_date=None, to_date=None, customer=None, status=None, company=None):
	conditions = ["si.is_return = 0"]
	params = {}

	if company:
		conditions.append("si.company = %(company)s")
		params["company"] = company
	if from_date:
		conditions.append("si.posting_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("si.posting_date <= %(to_date)s")
		params["to_date"] = to_date
	if customer:
		conditions.append("si.customer = %(customer)s")
		params["customer"] = customer

	today_val = today()
	if status == "Paga":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount <= 0")
	elif status == "Em Dívida":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount > 0 AND si.due_date >= %(today_val)s")
		params["today_val"] = today_val
	elif status == "Vencida":
		conditions.append("si.docstatus = 1 AND si.outstanding_amount > 0 AND si.due_date < %(today_val)s")
		params["today_val"] = today_val
	elif status == "Rascunho":
		conditions.append("si.docstatus = 0")
	else:
		conditions.append("si.docstatus = 1")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			si.name               AS invoice,
			si.customer,
			si.customer_name,
			si.posting_date,
			si.due_date,
			si.grand_total,
			si.outstanding_amount,
			si.docstatus
		FROM `tabSales Invoice` si
		WHERE {where}
		ORDER BY si.posting_date DESC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	today_date = getdate(today_val)
	posted_rows = [r for r in rows if r.docstatus == 1]
	draft_rows = [r for r in rows if r.docstatus == 0]

	for r in posted_rows:
		paid = float(r.grand_total or 0) - float(r.outstanding_amount or 0)
		r.paid = round(paid, 2)
		if float(r.outstanding_amount or 0) <= 0:
			r.display_status = "Paga"
		elif getdate(r.due_date) < today_date:
			r.display_status = "Vencida"
		else:
			r.display_status = "Em Dívida"

	for r in draft_rows:
		r.display_status = "Rascunho"
		r.paid = 0.0

	overdue_rows = [r for r in posted_rows if r.display_status == "Vencida"]
	summary = {
		"count": len(posted_rows),
		"draft_count": len(draft_rows),
		"total_invoiced": round(sum(float(r.grand_total or 0) for r in posted_rows), 2),
		"total_paid": round(sum(r.paid for r in posted_rows), 2),
		"total_outstanding": round(sum(float(r.outstanding_amount or 0) for r in posted_rows), 2),
		"total_overdue": round(sum(float(r.outstanding_amount or 0) for r in overdue_rows), 2),
		"overdue_count": len(overdue_rows),
	}
	return rows, summary


def _query_upcoming(from_date=None, to_date=None, customer=None, status=None, company=None):
	conditions = ["ar.reference_doctype = 'Sales Invoice'"]
	params = {}

	if company:
		conditions.append("si.company = %(company)s")
		params["company"] = company
	if from_date:
		conditions.append("ar.next_schedule_date >= %(from_date)s")
		params["from_date"] = from_date
	if to_date:
		conditions.append("ar.next_schedule_date <= %(to_date)s")
		params["to_date"] = to_date
	if customer:
		conditions.append("si.customer = %(customer)s")
		params["customer"] = customer

	today_val = today()
	if status == "Activo":
		conditions.append("ar.disabled = 0 AND (ar.end_date IS NULL OR ar.end_date >= %(today_val)s)")
		params["today_val"] = today_val
	elif status == "Concluído":
		conditions.append("ar.disabled = 0 AND ar.end_date IS NOT NULL AND ar.end_date < %(today_val)s")
		params["today_val"] = today_val
	elif status == "Desactivado":
		conditions.append("ar.disabled = 1")

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT
			ar.name                AS auto_repeat,
			ar.reference_document  AS invoice_ref,
			ar.next_schedule_date,
			ar.frequency,
			ar.disabled,
			ar.end_date,
			si.customer,
			si.customer_name,
			si.grand_total
		FROM `tabAuto Repeat` ar
		INNER JOIN `tabSales Invoice` si ON si.name = ar.reference_document
		WHERE {where}
		ORDER BY ar.next_schedule_date ASC
		LIMIT 1000
		""",
		params,
		as_dict=True,
	)

	today_date = getdate(today_val)
	for r in rows:
		if r.disabled:
			r.display_status = "Desactivado"
		elif r.end_date and getdate(r.end_date) < today_date:
			r.display_status = "Concluído"
		else:
			r.display_status = "Activo"

	total_expected = sum(float(r.grand_total or 0) for r in rows)
	next_dates = [getdate(r.next_schedule_date) for r in rows if r.next_schedule_date]

	summary = {
		"count": len(rows),
		"total_expected": round(total_expected, 2),
		"next_date": min(next_dates).isoformat() if next_dates else None,
	}
	return rows, summary


@frappe.whitelist()
def get_invoices(from_date=None, to_date=None, customer=None, status=None, company=None):
	"""Return filtered Sales Invoice rows and summary stats."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, summary = _query_invoices(from_date, to_date, customer, status, company)
	return {"rows": rows, "summary": summary}


@frappe.whitelist()
def get_upcoming_invoices(from_date=None, to_date=None, customer=None, status=None, company=None):
	"""Return upcoming Auto Repeat-generated Sales Invoices and summary stats."""
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Auto Repeat", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, summary = _query_upcoming(from_date, to_date, customer, status, company)
	return {"rows": rows, "summary": summary}


@frappe.whitelist()
def get_default_fiscal_year(company=None):
	"""Return the Fiscal Year whose date range contains today's actual date."""
	if not frappe.has_permission("Fiscal Year", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	today_val = today()
	fy = frappe.db.get_value(
		"Fiscal Year",
		{"year_start_date": ["<=", today_val], "year_end_date": [">=", today_val]},
		["name", "year_start_date", "year_end_date"],
		as_dict=True,
	)
	if not fy:
		return None
	return {
		"name": fy.name,
		"year_start_date": fy.year_start_date,
		"year_end_date": fy.year_end_date,
	}


# ───────────────────────────── Exports ─────────────────────────────

INVOICE_HEADERS = ["Cliente", "Nº Factura", "Emissão", "Vencimento", "Total", "Pago", "Em Dívida", "Estado"]
UPCOMING_HEADERS = ["Cliente", "Factura de Referência", "Próxima Data", "Frequência", "Valor Esperado", "Estado"]


def _invoice_table(rows):
	data = [[_(h) for h in INVOICE_HEADERS]]
	for r in rows:
		data.append(
			[
				r.customer_name or r.customer,
				r.invoice,
				formatdate(r.posting_date),
				formatdate(r.due_date) if r.due_date else "",
				flt(r.grand_total, 2),
				flt(r.paid, 2),
				flt(r.outstanding_amount, 2),
				_(r.display_status),
			]
		)
	data.append(
		[
			_("Total"),
			"",
			"",
			"",
			flt(sum(flt(r.grand_total) for r in rows), 2),
			flt(sum(flt(r.paid) for r in rows), 2),
			flt(sum(flt(r.outstanding_amount) for r in rows), 2),
			"",
		]
	)
	return data


def _upcoming_table(rows):
	data = [[_(h) for h in UPCOMING_HEADERS]]
	for r in rows:
		data.append(
			[
				r.customer_name or r.customer,
				r.invoice_ref,
				formatdate(r.next_schedule_date) if r.next_schedule_date else "",
				_(FREQ_LABELS.get(r.frequency, r.frequency or "")),
				flt(r.grand_total, 2),
				_(r.display_status),
			]
		)
	data.append([_("Total"), "", "", "", flt(sum(flt(r.grand_total) for r in rows), 2), ""])
	return data


def _pdf_options(orientation=None):
	if orientation in ("Portrait", "Landscape"):
		return {"orientation": orientation}
	return None


def _get_letterhead_html(letter_head=None):
	name = letter_head or frappe.db.get_value("Letter Head", {"is_default": 1, "disabled": 0}, "name")
	if not name:
		return ""
	doc = frappe.get_cached_doc("Letter Head", name)
	if getattr(doc, "content", None):
		return doc.content
	if getattr(doc, "image", None):
		return f'<img src="{doc.image}" style="max-height:120px;">'
	return ""


@frappe.whitelist()
def get_letterhead_html(letter_head=None):
	if not frappe.has_permission("Letter Head", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return _get_letterhead_html(letter_head)


def _html_page(title, headers, body_rows, right_align_cols=(), letterhead_html=""):
	head_html = "".join(f"<th>{html_escape(str(h))}</th>" for h in headers)

	def _row_html(cells, is_total=False):
		tds = []
		for i, cell in enumerate(cells):
			style = "text-align:right" if i in right_align_cols else ""
			tds.append(f'<td style="{style}">{html_escape(str(cell))}</td>')
		cls = ' class="total-row"' if is_total else ""
		return f"<tr{cls}>{''.join(tds)}</tr>"

	rows_html = "".join(_row_html(row, is_total=(i == len(body_rows) - 1)) for i, row in enumerate(body_rows))
	letterhead_block = f'<div class="letterhead">{letterhead_html}</div>' if letterhead_html else ""

	return f"""
	<html>
	<head>
		<meta charset="utf-8">
		<style>
			body {{ font-family: Arial, sans-serif; font-size: 11px; color: #111; }}
			.letterhead {{ margin-bottom: 14px; }}
			h2 {{ margin: 0 0 4px 0; }}
			.meta {{ color: #666; margin-bottom: 14px; }}
			table {{ width: 100%; border-collapse: collapse; }}
			th, td {{ border: 1px solid #ccc; padding: 5px 8px; }}
			th {{ background: #f3f4f6; text-align: left; }}
			.total-row td {{ font-weight: bold; background: #f9fafb; }}
		</style>
	</head>
	<body>
		{letterhead_block}
		<h2>{html_escape(title)}</h2>
		<div class="meta">{now_datetime().strftime("%d-%m-%Y %H:%M")}</div>
		<table>
			<thead><tr>{head_html}</tr></thead>
			<tbody>{rows_html}</tbody>
		</table>
	</body>
	</html>
	"""


@frappe.whitelist()
def export_invoices_xlsx(from_date=None, to_date=None, customer=None, status=None, company=None):
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, _summary = _query_invoices(from_date, to_date, customer, status, company)
	xlsx_file = make_xlsx(_invoice_table(rows), "Monitor de Facturas")
	frappe.response["filename"] = "monitor-facturas.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def export_invoices_pdf(
	from_date=None,
	to_date=None,
	customer=None,
	status=None,
	company=None,
	with_letterhead=0,
	letter_head=None,
	orientation=None,
):
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, _summary = _query_invoices(from_date, to_date, customer, status, company)
	table = _invoice_table(rows)
	letterhead_html = _get_letterhead_html(letter_head) if cint(with_letterhead) else ""
	html = _html_page(
		_("Monitor de Facturas"), table[0], table[1:], right_align_cols=(4, 5, 6), letterhead_html=letterhead_html
	)
	frappe.response["filename"] = "monitor-facturas.pdf"
	frappe.response["filecontent"] = get_pdf(html, options=_pdf_options(orientation))
	frappe.response["type"] = "pdf"


@frappe.whitelist()
def export_upcoming_xlsx(from_date=None, to_date=None, customer=None, status=None, company=None):
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Auto Repeat", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, _summary = _query_upcoming(from_date, to_date, customer, status, company)
	xlsx_file = make_xlsx(_upcoming_table(rows), "Proximas Facturas")
	frappe.response["filename"] = "proximas-facturas.xlsx"
	frappe.response["filecontent"] = xlsx_file.getvalue()
	frappe.response["type"] = "binary"


@frappe.whitelist()
def export_upcoming_pdf(
	from_date=None,
	to_date=None,
	customer=None,
	status=None,
	company=None,
	with_letterhead=0,
	letter_head=None,
	orientation=None,
):
	if not frappe.has_permission("Sales Invoice", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if not frappe.has_permission("Auto Repeat", "read"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	rows, _summary = _query_upcoming(from_date, to_date, customer, status, company)
	table = _upcoming_table(rows)
	letterhead_html = _get_letterhead_html(letter_head) if cint(with_letterhead) else ""
	html = _html_page(
		_("Próximas Facturas"), table[0], table[1:], right_align_cols=(4,), letterhead_html=letterhead_html
	)
	frappe.response["filename"] = "proximas-facturas.pdf"
	frappe.response["filecontent"] = get_pdf(html, options=_pdf_options(orientation))
	frappe.response["type"] = "pdf"
