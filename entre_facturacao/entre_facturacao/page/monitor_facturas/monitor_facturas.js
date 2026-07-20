frappe.pages["monitor-facturas"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Monitor de Facturas"),
		single_column: true,
	});
	new MonitorFacturas(page);
};

const MF_FREQ_LABELS = {
	Daily: __("Diária"),
	Weekly: __("Semanal"),
	Monthly: __("Mensal"),
	Quarterly: __("Trimestral"),
	"Half-yearly": __("Semestral"),
	Yearly: __("Anual"),
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
			<div class="mf-tabs">
				<button class="mf-tab-btn active" data-tab="invoices">${__("Facturas")}</button>
				<button class="mf-tab-btn" data-tab="upcoming">${__("Próximas Facturas")}</button>
			</div>
			<div class="mf-panel" id="mf-panel-invoices"></div>
			<div class="mf-panel" id="mf-panel-upcoming" style="display:none"></div>
		</div>`);

		this._build_invoices_panel();
		this._build_upcoming_panel();
		this._bind_tabs();
	}

	_bind_tabs() {
		this.$body.find(".mf-tab-btn").on("click", (e) => {
			const tab = $(e.currentTarget).data("tab");
			this.$body.find(".mf-tab-btn").removeClass("active");
			$(e.currentTarget).addClass("active");
			this.$body.find("#mf-panel-invoices").toggle(tab === "invoices");
			this.$body.find("#mf-panel-upcoming").toggle(tab === "upcoming");
			if (tab === "upcoming" && !this._upcoming_loaded) {
				this._upcoming_loaded = true;
				this.search_upcoming();
			}
		});
	}

	/* ───────────────────── Tab 1: Facturas ───────────────────── */

	_build_invoices_panel() {
		const $panel = this.$body.find("#mf-panel-invoices");
		$panel.html(`
			<div class="mf-filters">
				<div class="mf-row">
					<div class="mf-fg" id="mf-company-wrap">
						<label>${__("Empresa")}</label>
					</div>
					<div class="mf-fg mf-fg--grow" id="mf-customer-wrap">
						<label>${__("Cliente")}</label>
					</div>
					<div class="mf-fg">
						<label>${__("Mês")}</label>
						<input id="mf-month" type="month">
					</div>
					<div class="mf-fg" id="mf-fiscal-year-wrap">
						<label>${__("Ano Fiscal")}</label>
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
							<option value="Rascunho">${__("Rascunho")}</option>
						</select>
					</div>
					<div class="mf-fg mf-fg--btns">
						<button class="btn btn-primary btn-sm" id="mf-search">${__("Pesquisar")}</button>
						<button class="btn btn-default btn-sm"  id="mf-clear">${__("Limpar")}</button>
						<div class="dropdown">
							<button class="btn btn-default btn-sm dropdown-toggle" type="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
								${__("Ações")}
							</button>
							<div class="dropdown-menu dropdown-menu-right">
								<a class="dropdown-item" href="#" id="mf-print">${__("Imprimir")}</a>
								<a class="dropdown-item" href="#" id="mf-export-xlsx">${__("Exportar Excel")}</a>
								<a class="dropdown-item" href="#" id="mf-export-pdf">${__("Exportar PDF")}</a>
							</div>
						</div>
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
						<th>${__("Título")}</th>
						<th>${__("Emissão")}</th>
						<th>${__("Vencimento")}</th>
						<th class="mf-r">${__("Total")}</th>
						<th class="mf-r">${__("Pago")}</th>
						<th class="mf-r">${__("Em Dívida")}</th>
						<th>${__("Estado")}</th>
						<th></th>
					</tr></thead>
					<tbody id="mf-tbody"></tbody>
					<tfoot id="mf-tfoot"></tfoot>
				</table>
			</div>

			<div class="mf-empty" id="mf-empty" style="display:none">
				${__("Nenhuma factura encontrada.")}
			</div>`);

		this.company_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "company",
				options: "Company",
			},
			parent: this.$body.find("#mf-company-wrap")[0],
			render_input: true,
		});
		this.company_control.refresh();
		this.company_control.set_value(frappe.defaults.get_default("company") || "");
		this.company_control.$input.on("change awesomplete-selectcomplete", () => this.search());

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
		this.customer_control.$input.on("change awesomplete-selectcomplete", () => this.search());

		this.fiscal_year_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "fiscal_year",
				options: "Fiscal Year",
				placeholder: __("Automático"),
			},
			parent: this.$body.find("#mf-fiscal-year-wrap")[0],
			render_input: true,
		});
		this.fiscal_year_control.refresh();
		this.fiscal_year_control.$input.on("change awesomplete-selectcomplete", async () => {
			const fy = this.fiscal_year_control.get_value();
			if (fy) {
				const { message } = await frappe.db.get_value("Fiscal Year", fy, [
					"year_start_date",
					"year_end_date",
				]);
				this._apply_fiscal_year(message.year_start_date, message.year_end_date, "#mf-from", "#mf-to", "#mf-month");
			}
			this.search();
		});

		this.$body.find("#mf-search").on("click", () => this.search());
		this.$body.find("#mf-clear").on("click", () => this._clear());
		this.$body.find("#mf-status").on("change", () => this.search());
		this.$body.find("#mf-month").on("change", (e) => {
			this._apply_month(e.target.value, "#mf-from", "#mf-to");
			this.fiscal_year_control.set_value("");
			this.search();
		});
		this.$body.find("#mf-from, #mf-to").on("change", () => {
			this.$body.find("#mf-month").val("");
			this.fiscal_year_control.set_value("");
			this.search();
		});
		this.$body.find("#mf-print").on("click", (e) => {
			e.preventDefault();
			this._show_print_options((opts) => this._print(opts));
		});
		this.$body.find("#mf-export-xlsx").on("click", (e) => {
			e.preventDefault();
			this._export("entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.export_invoices_xlsx", this._get_filters());
		});
		this.$body.find("#mf-export-pdf").on("click", (e) => {
			e.preventDefault();
			this._show_print_options((opts) =>
				this._export(
					"entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.export_invoices_pdf",
					{ ...this._get_filters(), ...opts }
				)
			);
		});

		this._init_default_fiscal_year(
			this.company_control.get_value(),
			this.fiscal_year_control,
			"#mf-from",
			"#mf-to",
			"#mf-month"
		).then(() => this.search());
	}

	_get_filters() {
		return {
			company: this.company_control.get_value() || "",
			from_date: this.$body.find("#mf-from").val() || "",
			to_date: this.$body.find("#mf-to").val() || "",
			customer: this.customer_control.get_value() || "",
			status: this.$body.find("#mf-status").val() || "",
		};
	}

	async search() {
		const $btn = this.$body.find("#mf-search").prop("disabled", true).text(__("A pesquisar…"));
		try {
			const r = await frappe.call({
				method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_invoices",
				args: this._get_filters(),
			});
			if (r.message) this._render(r.message);
		} finally {
			$btn.prop("disabled", false).text(__("Pesquisar"));
		}
	}

	_render({ rows, summary }) {
		const $sum = this.$body.find("#mf-summary").show();
		$sum.find("#mf-s-total").text(format_currency(summary.total_invoiced));
		$sum.find("#mf-s-count").text(
			summary.draft_count
				? __("{0} factura(s) · {1} rascunho(s)", [summary.count, summary.draft_count])
				: __("{0} factura(s)", [summary.count])
		);
		$sum.find("#mf-s-paid").text(format_currency(summary.total_paid));
		$sum.find("#mf-s-outstanding").text(format_currency(summary.total_outstanding));
		$sum.find("#mf-s-overdue").text(format_currency(summary.total_overdue));
		$sum.find("#mf-s-overdue-count").text(__("{0} vencida(s)", [summary.overdue_count]));

		const BADGE = {
			"Paga": "mf-b--green",
			"Em Dívida": "mf-b--orange",
			"Vencida": "mf-b--red",
			"Rascunho": "mf-b--grey",
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
				<td>${frappe.utils.escape_html(r.invoice_title || "")}</td>
				<td>${frappe.datetime.str_to_user(r.posting_date)}</td>
				<td>${frappe.datetime.str_to_user(r.due_date)}</td>
				<td class="mf-r">${format_currency(r.grand_total)}</td>
				<td class="mf-r">${format_currency(r.paid)}</td>
				<td class="mf-r">${format_currency(r.outstanding_amount)}</td>
				<td><span class="mf-b ${BADGE[r.display_status] || ""}">${r.display_status}</span></td>
				<td>
					<a href="/app/sales-invoice/${encodeURIComponent(r.invoice)}" target="_blank" class="mf-link" title="${__("Abrir factura")}">↗</a>
					<a href="/app/query-report/Extrato%20da%20Factura?factura=${encodeURIComponent(r.invoice)}" target="_blank" class="mf-link" title="${__("Extrato da Factura")}">Σ</a>
				</td>
			</tr>`
			)
			.join("");

		this.$body.find("#mf-tbody").html(html);

		const total_row = rows.reduce(
			(acc, r) => {
				acc.grand_total += Number(r.grand_total) || 0;
				acc.paid += Number(r.paid) || 0;
				acc.outstanding_amount += Number(r.outstanding_amount) || 0;
				return acc;
			},
			{ grand_total: 0, paid: 0, outstanding_amount: 0 }
		);
		this.$body.find("#mf-tfoot").html(`
			<tr class="mf-tfoot-row">
				<td colspan="5">${__("Total")}</td>
				<td class="mf-r">${format_currency(total_row.grand_total)}</td>
				<td class="mf-r">${format_currency(total_row.paid)}</td>
				<td class="mf-r">${format_currency(total_row.outstanding_amount)}</td>
				<td></td>
				<td></td>
			</tr>`);
	}

	_clear() {
		this.$body.find("#mf-status").val("");
		this.$body.find("#mf-month, #mf-from, #mf-to").val("");
		this.customer_control.set_value("");
		this.fiscal_year_control.set_value("");
		this.$body.find("#mf-summary, #mf-tbl-wrap, #mf-empty").hide();
		this.search();
	}

	/* ─────────────────── Tab 2: Próximas Facturas ─────────────────── */

	_build_upcoming_panel() {
		const $panel = this.$body.find("#mf-panel-upcoming");
		$panel.html(`
			<div class="mf-filters">
				<div class="mf-row">
					<div class="mf-fg" id="mf-up-company-wrap">
						<label>${__("Empresa")}</label>
					</div>
					<div class="mf-fg mf-fg--grow" id="mf-up-customer-wrap">
						<label>${__("Cliente")}</label>
					</div>
					<div class="mf-fg">
						<label>${__("Mês")}</label>
						<input id="mf-up-month" type="month">
					</div>
					<div class="mf-fg" id="mf-up-fiscal-year-wrap">
						<label>${__("Ano Fiscal")}</label>
					</div>
					<div class="mf-fg">
						<label>${__("De")}</label>
						<input id="mf-up-from" type="date">
					</div>
					<div class="mf-fg">
						<label>${__("Até")}</label>
						<input id="mf-up-to" type="date">
					</div>
					<div class="mf-fg">
						<label>${__("Estado")}</label>
						<select id="mf-up-status">
							<option value="">${__("Todos")}</option>
							<option value="Activo">${__("Activo")}</option>
							<option value="Concluído">${__("Concluído")}</option>
							<option value="Desactivado">${__("Desactivado")}</option>
						</select>
					</div>
					<div class="mf-fg mf-fg--btns">
						<button class="btn btn-primary btn-sm" id="mf-up-search">${__("Pesquisar")}</button>
						<button class="btn btn-default btn-sm"  id="mf-up-clear">${__("Limpar")}</button>
						<div class="dropdown">
							<button class="btn btn-default btn-sm dropdown-toggle" type="button" data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
								${__("Ações")}
							</button>
							<div class="dropdown-menu dropdown-menu-right">
								<a class="dropdown-item" href="#" id="mf-up-print">${__("Imprimir")}</a>
								<a class="dropdown-item" href="#" id="mf-up-export-xlsx">${__("Exportar Excel")}</a>
								<a class="dropdown-item" href="#" id="mf-up-export-pdf">${__("Exportar PDF")}</a>
							</div>
						</div>
					</div>
				</div>
			</div>

			<div class="mf-summary" id="mf-up-summary" style="display:none">
				<div class="mf-card mf-card--blue">
					<div class="mf-card-lbl">${__("Total Esperado")}</div>
					<div class="mf-card-val" id="mf-up-s-total">—</div>
					<div class="mf-card-sub" id="mf-up-s-count"></div>
				</div>
				<div class="mf-card mf-card--green">
					<div class="mf-card-lbl">${__("Facturas Esperadas")}</div>
					<div class="mf-card-val" id="mf-up-s-num">—</div>
				</div>
				<div class="mf-card mf-card--orange">
					<div class="mf-card-lbl">${__("Próxima Data")}</div>
					<div class="mf-card-val" id="mf-up-s-next">—</div>
				</div>
			</div>

			<div class="mf-tbl-wrap" id="mf-up-tbl-wrap" style="display:none">
				<table class="mf-tbl">
					<thead><tr>
						<th>${__("Cliente")}</th>
						<th>${__("Factura de Referência")}</th>
						<th>${__("Título")}</th>
						<th>${__("Próxima Data")}</th>
						<th>${__("Frequência")}</th>
						<th class="mf-r">${__("Valor Esperado")}</th>
						<th>${__("Estado")}</th>
						<th></th>
					</tr></thead>
					<tbody id="mf-up-tbody"></tbody>
					<tfoot id="mf-up-tfoot"></tfoot>
				</table>
			</div>

			<div class="mf-empty" id="mf-up-empty" style="display:none">
				${__("Nenhuma factura futura encontrada.")}
			</div>`);

		this.upcoming_company_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "company",
				options: "Company",
			},
			parent: this.$body.find("#mf-up-company-wrap")[0],
			render_input: true,
		});
		this.upcoming_company_control.refresh();
		this.upcoming_company_control.set_value(frappe.defaults.get_default("company") || "");
		this.upcoming_company_control.$input.on("change awesomplete-selectcomplete", () =>
			this.search_upcoming()
		);

		this.upcoming_customer_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "customer",
				options: "Customer",
				placeholder: __("Todos"),
			},
			parent: this.$body.find("#mf-up-customer-wrap")[0],
			render_input: true,
		});
		this.upcoming_customer_control.refresh();
		this.upcoming_customer_control.$input.on("change awesomplete-selectcomplete", () =>
			this.search_upcoming()
		);

		this.upcoming_fiscal_year_control = frappe.ui.form.make_control({
			df: {
				fieldtype: "Link",
				fieldname: "fiscal_year",
				options: "Fiscal Year",
				placeholder: __("Automático"),
			},
			parent: this.$body.find("#mf-up-fiscal-year-wrap")[0],
			render_input: true,
		});
		this.upcoming_fiscal_year_control.refresh();
		this.upcoming_fiscal_year_control.$input.on("change awesomplete-selectcomplete", async () => {
			const fy = this.upcoming_fiscal_year_control.get_value();
			if (fy) {
				const { message } = await frappe.db.get_value("Fiscal Year", fy, [
					"year_start_date",
					"year_end_date",
				]);
				this._apply_fiscal_year(
					message.year_start_date,
					message.year_end_date,
					"#mf-up-from",
					"#mf-up-to",
					"#mf-up-month"
				);
			}
			this.search_upcoming();
		});

		this.$body.find("#mf-up-search").on("click", () => this.search_upcoming());
		this.$body.find("#mf-up-clear").on("click", () => this._clear_upcoming());
		this.$body.find("#mf-up-status").on("change", () => this.search_upcoming());
		this.$body.find("#mf-up-month").on("change", (e) => {
			this._apply_month(e.target.value, "#mf-up-from", "#mf-up-to");
			this.upcoming_fiscal_year_control.set_value("");
			this.search_upcoming();
		});
		this.$body.find("#mf-up-from, #mf-up-to").on("change", () => {
			this.$body.find("#mf-up-month").val("");
			this.upcoming_fiscal_year_control.set_value("");
			this.search_upcoming();
		});
		this.$body.find("#mf-up-print").on("click", (e) => {
			e.preventDefault();
			this._show_print_options((opts) => this._print(opts));
		});
		this.$body.find("#mf-up-export-xlsx").on("click", (e) => {
			e.preventDefault();
			this._export(
				"entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.export_upcoming_xlsx",
				this._get_upcoming_filters()
			);
		});
		this.$body.find("#mf-up-export-pdf").on("click", (e) => {
			e.preventDefault();
			this._show_print_options((opts) =>
				this._export(
					"entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.export_upcoming_pdf",
					{ ...this._get_upcoming_filters(), ...opts }
				)
			);
		});
		this.$body.find("#mf-up-tbody").on("click", ".mf-toggle-btn", (e) => {
			this._toggle_auto_repeat($(e.currentTarget));
		});

		this._init_default_fiscal_year(
			this.upcoming_company_control.get_value(),
			this.upcoming_fiscal_year_control,
			"#mf-up-from",
			"#mf-up-to",
			"#mf-up-month"
		);
	}

	_toggle_auto_repeat($btn) {
		const auto_repeat = $btn.data("auto-repeat");
		const next_disabled = cint($btn.data("disabled")) ? 0 : 1;
		$btn.prop("disabled", true);
		frappe.call({
			method: "entre_facturacao.auto_repeat.toggle_auto_repeat",
			args: { auto_repeat, disabled: next_disabled },
			callback: (r) => {
				if (r.message === undefined) return;
				frappe.show_alert({
					message: next_disabled ? __("Repetição pausada.") : __("Repetição activada."),
					indicator: next_disabled ? "orange" : "green",
				});
				this.search_upcoming();
			},
			always: () => $btn.prop("disabled", false),
		});
	}

	_get_upcoming_filters() {
		return {
			company: this.upcoming_company_control.get_value() || "",
			from_date: this.$body.find("#mf-up-from").val() || "",
			to_date: this.$body.find("#mf-up-to").val() || "",
			customer: this.upcoming_customer_control.get_value() || "",
			status: this.$body.find("#mf-up-status").val() || "",
		};
	}

	async search_upcoming() {
		const $btn = this.$body.find("#mf-up-search").prop("disabled", true).text(__("A pesquisar…"));
		try {
			const r = await frappe.call({
				method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_upcoming_invoices",
				args: this._get_upcoming_filters(),
			});
			if (r.message) this._render_upcoming(r.message);
		} finally {
			$btn.prop("disabled", false).text(__("Pesquisar"));
		}
	}

	_render_upcoming({ rows, summary }) {
		const $sum = this.$body.find("#mf-up-summary").show();
		$sum.find("#mf-up-s-total").text(format_currency(summary.total_expected));
		$sum.find("#mf-up-s-count").text(__("{0} factura(s)", [summary.count]));
		$sum.find("#mf-up-s-num").text(summary.count);
		$sum.find("#mf-up-s-next").text(
			summary.next_date ? frappe.datetime.str_to_user(summary.next_date) : "—"
		);

		const BADGE = {
			"Activo": "mf-b--green",
			"Concluído": "mf-b--orange",
			"Desactivado": "mf-b--red",
		};

		if (!rows.length) {
			this.$body.find("#mf-up-tbl-wrap").hide();
			this.$body.find("#mf-up-empty").show();
			return;
		}
		this.$body.find("#mf-up-empty").hide();
		this.$body.find("#mf-up-tbl-wrap").show();

		const html = rows
			.map(
				(r) => `
			<tr>
				<td>${frappe.utils.escape_html(r.customer_name || r.customer)}</td>
				<td><a href="/app/sales-invoice/${encodeURIComponent(r.invoice_ref)}" target="_blank" class="mf-ref-link">${frappe.utils.escape_html(r.invoice_ref)}</a></td>
				<td>${frappe.utils.escape_html(r.invoice_title || "")}</td>
				<td>${r.next_schedule_date ? frappe.datetime.str_to_user(r.next_schedule_date) : "—"}</td>
				<td>${frappe.utils.escape_html(MF_FREQ_LABELS[r.frequency] || r.frequency || "—")}</td>
				<td class="mf-r">${format_currency(r.grand_total)}</td>
				<td><span class="mf-b ${BADGE[r.display_status] || ""}">${r.display_status}</span></td>
				<td>
					<button
						class="btn btn-default btn-sm mf-toggle-btn"
						data-auto-repeat="${r.auto_repeat}"
						data-disabled="${r.disabled ? 1 : 0}"
					>${r.disabled ? __("Activar") : __("Pausar")}</button>
					<a href="/app/auto-repeat/${encodeURIComponent(r.auto_repeat)}" target="_blank" class="mf-link" title="${__("Editar repetição automática")}">✎</a>
				</td>
			</tr>`
			)
			.join("");

		this.$body.find("#mf-up-tbody").html(html);

		const total_expected = rows.reduce((acc, r) => acc + (Number(r.grand_total) || 0), 0);
		this.$body.find("#mf-up-tfoot").html(`
			<tr class="mf-tfoot-row">
				<td colspan="5">${__("Total")}</td>
				<td class="mf-r">${format_currency(total_expected)}</td>
				<td></td>
				<td></td>
			</tr>`);
	}

	_clear_upcoming() {
		this.$body.find("#mf-up-status").val("");
		this.$body.find("#mf-up-month, #mf-up-from, #mf-up-to").val("");
		this.upcoming_customer_control.set_value("");
		this.upcoming_fiscal_year_control.set_value("");
		this.$body.find("#mf-up-summary, #mf-up-tbl-wrap, #mf-up-empty").hide();
		this.search_upcoming();
	}

	/* ───────────────────────── Shared ───────────────────────── */

	_apply_month(value, from_sel, to_sel) {
		if (!value) return;
		const [year, month] = value.split("-").map(Number);
		const pad = (n) => String(n).padStart(2, "0");
		const first = `${year}-${pad(month)}-01`;
		const last_day = new Date(year, month, 0).getDate();
		const last = `${year}-${pad(month)}-${pad(last_day)}`;
		this.$body.find(from_sel).val(first);
		this.$body.find(to_sel).val(last);
	}

	_apply_fiscal_year(year_start_date, year_end_date, from_sel, to_sel, month_sel) {
		this.$body.find(month_sel).val("");
		this.$body.find(from_sel).val(year_start_date);
		this.$body.find(to_sel).val(year_end_date);
	}

	async _init_default_fiscal_year(company, fy_control, from_sel, to_sel, month_sel) {
		if (!company) return;
		const r = await frappe.call({
			method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_default_fiscal_year",
			args: { company },
		});
		if (r.message) {
			fy_control.set_value(r.message.name);
			this._apply_fiscal_year(r.message.year_start_date, r.message.year_end_date, from_sel, to_sel, month_sel);
		}
	}

	_export(method, filters) {
		const params = new URLSearchParams(filters);
		window.open(`/api/method/${method}?${params.toString()}`, "_blank");
	}

	_show_print_options(callback) {
		const RETRATO = __("Retrato");
		const PAISAGEM = __("Paisagem");
		const dialog = new frappe.ui.Dialog({
			title: __("Opções de Impressão"),
			fields: [
				{
					fieldtype: "Check",
					fieldname: "with_letterhead",
					label: __("Incluir Cabeçalho"),
					default: 1,
				},
				{
					fieldtype: "Link",
					fieldname: "letter_head",
					label: __("Cabeçalho"),
					options: "Letter Head",
					depends_on: "with_letterhead",
					description: __("Deixe em branco para usar o cabeçalho predefinido."),
				},
				{
					fieldtype: "Select",
					fieldname: "orientation",
					label: __("Orientação"),
					options: [RETRATO, PAISAGEM],
					default: RETRATO,
				},
			],
			primary_action_label: __("Confirmar"),
			primary_action: (values) => {
				dialog.hide();
				callback({
					with_letterhead: values.with_letterhead ? 1 : 0,
					letter_head: values.letter_head || "",
					orientation: values.orientation === PAISAGEM ? "Landscape" : "Portrait",
				});
			},
		});
		dialog.show();
	}

	async _print(opts) {
		let letterhead_html = "";
		if (opts.with_letterhead) {
			const r = await frappe.call({
				method: "entre_facturacao.entre_facturacao.page.monitor_facturas.monitor_facturas.get_letterhead_html",
				args: { letter_head: opts.letter_head || null },
			});
			letterhead_html = r.message || "";
		}

		const $letterhead = $(`<div class="mf-print-letterhead">${letterhead_html}</div>`);
		this.$body.find(".mf-wrap").prepend($letterhead);

		const style = document.createElement("style");
		style.textContent = `@page { size: A4 ${opts.orientation === "Landscape" ? "landscape" : "portrait"}; }`;
		document.head.appendChild(style);

		const cleanup = () => {
			$letterhead.remove();
			style.remove();
			window.removeEventListener("afterprint", cleanup);
		};
		window.addEventListener("afterprint", cleanup);

		window.print();
	}
}

function _mf_styles() {
	if (document.getElementById("mf-css")) return;
	const s = document.createElement("style");
	s.id = "mf-css";
	s.textContent = `
.mf-wrap { padding: 16px 20px; }

/* ── Tabs ─── */
.mf-tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border-color); }
.mf-tab-btn { background: none; border: none; padding: 10px 16px; font-size: 13px; font-weight: 600;
	color: var(--text-muted); cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.mf-tab-btn:hover { color: var(--text-color); }
.mf-tab-btn.active { color: var(--primary); border-bottom-color: var(--primary); }

/* ── Filters ─── */
.mf-filters { background: var(--fg-color); border: 1px solid var(--border-color);
	border-radius: 10px; padding: 14px 16px; margin-bottom: 16px; }
.mf-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
.mf-fg { display: flex; flex-direction: column; justify-content: flex-end; gap: 4px;
	min-width: 110px; min-height: 54px; }
.mf-fg--grow { flex: 1; min-width: 200px; }
.mf-fg--btns { flex-direction: row; gap: 6px; align-items: flex-end; min-width: unset; }
.mf-fg label { font-size: 11px; font-weight: 600; color: var(--text-muted);
	text-transform: uppercase; letter-spacing: .5px; line-height: 1; }
.mf-fg select, .mf-fg input[type=text], .mf-fg input[type=date], .mf-fg input[type=month],
.mf-fg .form-control {
	height: 32px !important; line-height: 30px; padding: 0 9px !important;
	border: 1.5px solid var(--border-color) !important; border-radius: 6px;
	font-size: 13px; background: var(--fg-color); color: var(--text-color);
	outline: none; box-sizing: border-box; transition: border-color .15s; margin: 0 !important; }
.mf-fg select:focus, .mf-fg input:focus, .mf-fg .form-control:focus { border-color: var(--primary); }
.mf-fg .form-group { margin-bottom: 0 !important; }
.mf-fg label.control-label { display: none !important; }
.mf-fg .help-box, .mf-fg .control-value, .mf-fg small.form-text { display: none !important; }

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
.mf-tfoot-row td { padding: 10px 12px; font-weight: 700; color: var(--text-color);
	background: var(--subtle-fg); border-top: 2px solid var(--border-color); border-bottom: none; }
.mf-r { text-align: right; font-variant-numeric: tabular-nums; }
.mf-b { font-size: 11px; font-weight: 600; padding: 3px 9px; border-radius: 12px; white-space: nowrap; }
.mf-b--green  { background: #dcfce7; color: #166534; }
.mf-b--orange { background: #fef3c7; color: #92400e; }
.mf-b--red    { background: #fee2e2; color: #991b1b; }
.mf-b--grey   { background: #e5e7eb; color: #374151; }
.mf-link { font-size: 15px; color: var(--text-muted); text-decoration: none; }
.mf-link:hover { color: var(--primary); }
.mf-link + .mf-link { margin-left: 8px; }
.mf-toggle-btn { font-size: 11px; padding: 2px 9px; height: auto; line-height: 1.4; }
.mf-toggle-btn + .mf-link { margin-left: 8px; }
.mf-ref-link { color: var(--text-color); text-decoration: none; }
.mf-ref-link:hover { color: var(--primary); text-decoration: underline; }
.mf-empty { text-align: center; padding: 48px 20px; color: var(--text-muted); font-size: 14px; }

/* ── Print ─── */
.mf-print-letterhead { display: none; }
@media print {
	.navbar, .page-head, .page-actions, .standard-sidebar, .body-sidebar,
	.mf-tabs, .mf-filters { display: none !important; }
	.mf-wrap { padding: 0; }
	.mf-print-letterhead { display: block; margin-bottom: 14px; }
	.mf-tbl th:last-child, .mf-tbl td:last-child { display: none; }
	.mf-summary { break-inside: avoid; }
	.mf-tbl-wrap { border: none; }
}
	`;
	document.head.appendChild(s);
}
