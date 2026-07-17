frappe.pages["monitor-facturas"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Facturas"),
		single_column: true,
	});
	new MonitorFacturas(page);
};

class MonitorFacturas {
	constructor(page) {
		this.page = page;
		this.$body = $(page.body);
		this._build();
	}

	_build() {
		_mf_styles();
		this.$body.html(`
		<div class="mf-wrap">
			<div class="mf-filters">
				<div class="mf-row">
					<div class="mf-fg mf-fg--grow" id="mf-customer-wrap">
						<label>${__("Cliente")}</label>
					</div>
					<div class="mf-fg">
						<label>${__("Mês")}</label>
						<input id="mf-month" type="month">
					</div>
					<div class="mf-fg">
						<label>${__("De")}</label>
						<input id="mf-from" type="date">
					</div>
					<div class="mf-fg">
						<label>${__("Até")}</label>
						<input id="mf-to" type="date">
					</div>
					<div class="mf-fg">
						<label>${__("Estado")}</label>
						<select id="mf-status">
							<option value="">${__("Todos")}</option>
							<option value="Paga">${__("Paga")}</option>
							<option value="Em Dívida">${__("Em Dívida")}</option>
							<option value="Vencida">${__("Vencida")}</option>
						</select>
					</div>
					<div class="mf-fg mf-fg--btns">
						<button class="btn btn-primary btn-sm" id="mf-search">${__("Pesquisar")}</button>
						<button class="btn btn-default btn-sm"  id="mf-clear">${__("Limpar")}</button>
					</div>
				</div>
			</div>

			<div class="mf-summary" id="mf-summary" style="display:none">
				<div class="mf-card mf-card--blue">
					<div class="mf-card-lbl">${__("Total Facturado")}</div>
					<div class="mf-card-val" id="mf-s-total">—</div>
					<div class="mf-card-sub" id="mf-s-count"></div>
				</div>
				<div class="mf-card mf-card--green">
					<div class="mf-card-lbl">${__("Total Pago")}</div>
					<div class="mf-card-val" id="mf-s-paid">—</div>
				</div>
				<div class="mf-card mf-card--orange">
					<div class="mf-card-lbl">${__("Total em Dívida")}</div>
					<div class="mf-card-val" id="mf-s-outstanding">—</div>
				</div>
				<div class="mf-card mf-card--red">
					<div class="mf-card-lbl">${__("Facturas Vencidas")}</div>
					<div class="mf-card-val" id="mf-s-overdue">—</div>
					<div class="mf-card-sub" id="mf-s-overdue-count"></div>
				</div>
			</div>

			<div class="mf-tbl-wrap" id="mf-tbl-wrap" style="display:none">
				<table class="mf-tbl">
					<thead><tr>
						<th>${__("Cliente")}</th>
						<th>${__("Nº Factura")}</th>
						<th>${__("Emissão")}</th>
						<th>${__("Vencimento")}</th>
						<th class="mf-r">${__("Total")}</th>
						<th class="mf-r">${__("Pago")}</th>
						<th class="mf-r">${__("Em Dívida")}</th>
						<th>${__("Estado")}</th>
						<th></th>
					</tr></thead>
					<tbody id="mf-tbody"></tbody>
				</table>
			</div>

			<div class="mf-empty" id="mf-empty" style="display:none">
				${__("Nenhuma factura encontrada.")}
			</div>
		</div>`);

		this._make_customer_control();
		this._bind();
	}

	_make_customer_control() {
		this.customer_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "customer",
				options: "Customer",
				placeholder: __("Todos"),
			},
			parent: this.$body.find("#mf-customer-wrap")[0],
			render_input: true,
		});
		this.customer_control.refresh();
	}

	_bind() {
		this.$body.find("#mf-search").on("click", () => this.search());
		this.$body.find("#mf-clear").on("click", () => this._clear());
		this.$body.find("#mf-from, #mf-to").on("keydown", (e) => {
			if (e.key === "Enter") this.search();
		});
		this.$body.find("#mf-month").on("change", (e) => this._apply_month(e.target.value));
		this.$body.find("#mf-from, #mf-to").on("input", () => this.$body.find("#mf-month").val(""));
	}

	_apply_month(value) {
		if (!value) return;
		const [year, month] = value.split("-").map(Number);
		const pad = (n) => String(n).padStart(2, "0");
		const first = `${year}-${pad(month)}-01`;
		const last_day = new Date(year, month, 0).getDate();
		const last = `${year}-${pad(month)}-${pad(last_day)}`;
		this.$body.find("#mf-from").val(first);
		this.$body.find("#mf-to").val(last);
	}

	async search() {
		const $btn = this.$body.find("#mf-search").prop("disabled", true).text(__("A pesquisar…"));
		try {
			const r = await frappe.call({
				method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_invoices",
				args: {
					from_date: this.$body.find("#mf-from").val() || null,
					to_date: this.$body.find("#mf-to").val() || null,
					customer: this.customer_control.get_value() || null,
					status: this.$body.find("#mf-status").val() || null,
				},
			});
			if (r.message) this._render(r.message);
		} finally {
			$btn.prop("disabled", false).text(__("Pesquisar"));
		}
	}

	_render({ rows, summary }) {
		const $sum = this.$body.find("#mf-summary").show();
		$sum.find("#mf-s-total").text(format_currency(summary.total_invoiced));
		$sum.find("#mf-s-count").text(__("{0} factura(s)", [summary.count]));
		$sum.find("#mf-s-paid").text(format_currency(summary.total_paid));
		$sum.find("#mf-s-outstanding").text(format_currency(summary.total_outstanding));
		$sum.find("#mf-s-overdue").text(format_currency(summary.total_overdue));
		$sum.find("#mf-s-overdue-count").text(__("{0} vencida(s)", [summary.overdue_count]));

		const BADGE = {
			"Paga": "mf-b--green",
			"Em Dívida": "mf-b--orange",
			"Vencida": "mf-b--red",
		};

		if (!rows.length) {
			this.$body.find("#mf-tbl-wrap").hide();
			this.$body.find("#mf-empty").show();
			return;
		}
		this.$body.find("#mf-empty").hide();
		this.$body.find("#mf-tbl-wrap").show();

		const html = rows
			.map(
				(r) => `
			<tr>
				<td>${frappe.utils.escape_html(r.customer_name || r.customer)}</td>
				<td>${frappe.utils.escape_html(r.invoice)}</td>
				<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
				<td>${frappe.datetime.str_to_user(r.due_date)}</td>
				<td class="mf-r">${format_currency(r.grand_total)}</td>
				<td class="mf-r">${format_currency(r.paid)}</td>
				<td class="mf-r">${format_currency(r.outstanding_amount)}</td>
				<td><span class="mf-b ${BADGE[r.display_status] || ""}">${r.display_status}</span></td>
				<td><a href="/app/sales-invoice/${encodeURIComponent(r.invoice)}" target="_blank" class="mf-link" title="${__("Abrir factura")}">↗</a></td>
			</tr>`
			)
			.join("");

		this.$body.find("#mf-tbody").html(html);
	}

	_clear() {
		this.$body.find("#mf-status").val("");
		this.$body.find("#mf-month, #mf-from, #mf-to").val("");
		this.customer_control.set_value("");
		this.$body.find("#mf-summary, #mf-tbl-wrap, #mf-empty").hide();
	}
}

function _mf_styles() {
	if (document.getElementById("mf-css")) return;
	const s = document.createElement("style");
	s.id = "mf-css";
	s.textContent = `
.mf-wrap { padding: 16px 20px; }

/* ── Filters ─── */
.mf-filters { background: var(--fg-color); border: 1px solid var(--border-color);
	border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.mf-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.mf-fg { display: flex; flex-direction: column; gap: 4px; min-width: 110px; }
.mf-fg--grow { flex: 1; min-width: 200px; }
.mf-fg--btns { flex-direction: row; gap: 6px; align-items: flex-end; min-width: unset; }
.mf-fg label { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; }
.mf-fg select, .mf-fg input[type=text], .mf-fg input[type=date], .mf-fg input[type=month] {
	height: 32px; padding: 0 9px; border: 1.5px solid var(--border-color);
	border-radius: 6px; font-size: 13px; background: var(--fg-color);
	color: var(--text-color); outline: none; transition: border-color .15s; }
.mf-fg select:focus, .mf-fg input:focus { border-color: var(--primary); }
#mf-customer-wrap .form-group { margin-bottom: 0; }
#mf-customer-wrap label.control-label { display: none; }

/* ── Summary cards ─── */
.mf-summary { display: flex; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.mf-card { flex: 1; min-width: 140px; padding: 14px 16px; border-radius: 10px;
	background: var(--fg-color); border: 1px solid var(--border-color);
	border-left: 4px solid transparent; }
.mf-card--blue   { border-left-color: #3b82f6; }
.mf-card--green  { border-left-color: #10b981; }
.mf-card--orange { border-left-color: #f59e0b; }
.mf-card--red    { border-left-color: #ef4444; }
.mf-card-lbl { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; margin-bottom: 5px; }
.mf-card-val { font-size: 20px; font-weight: 700; color: var(--text-color); }
.mf-card-sub { font-size: 12px; color: var(--text-muted); margin-top: 2px; }

/* ── Table ─── */
.mf-tbl-wrap { border: 1px solid var(--border-color); border-radius: 10px; overflow: hidden; }
.mf-tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.mf-tbl thead tr { background: var(--subtle-fg); }
.mf-tbl th { padding: 9px 12px; text-align: left; font-size: 11px; font-weight: 700;
	color: var(--text-muted); text-transform: uppercase; letter-spacing: .5px;
	border-bottom: 1px solid var(--border-color); white-space: nowrap; }
.mf-tbl td { padding: 9px 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
.mf-tbl tbody tr:last-child td { border-bottom: none; }
.mf-tbl tbody tr:hover { background: var(--subtle-fg); }
.mf-r { text-align: right; font-variant-numeric: tabular-nums; }
.mf-b { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }
.mf-b--green  { background: #dcfce7; color: #166534; }
.mf-b--orange { background: #fef3c7; color: #92400e; }
.mf-b--red    { background: #fee2e2; color: #991b1b; }
.mf-link { font-size: 15px; color: var(--text-muted); text-decoration: none; }
.mf-link:hover { color: var(--primary); }
.mf-empty { text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 14px; }
	`;
	document.head.appendChild(s);
}
