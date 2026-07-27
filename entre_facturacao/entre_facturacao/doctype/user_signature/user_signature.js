function render_signature_preview(frm) {
	const $wrapper = frm.get_field("signature_preview").$wrapper;
	$wrapper.empty();

	if (!frm.doc.signature_image) {
		$wrapper.html(`<div class="text-muted">${__("Upload a signature image to see a preview.")}</div>`);
		return;
	}

	const width = frm.doc.image_width || 150;
	const height = frm.doc.image_height || 60;
	const src = frappe.utils.escape_html(frm.doc.signature_image);

	$wrapper.html(`
		<div style="display:inline-block; padding:10px; border:1px dashed var(--border-color);">
			<img src="${src}" style="width:${width}px; height:${height}px; object-fit:contain;">
		</div>
		<div class="text-muted small" style="margin-top:4px;">${width}px &times; ${height}px</div>
	`);
}

frappe.ui.form.on("User Signature", {
	onload(frm) {
		frm.set_query("user", () => {
			if (frappe.user.has_role("System Manager")) {
				return {};
			}
			return {
				filters: { name: frappe.session.user },
			};
		});

		if (frm.is_new() && !frm.doc.user && !frappe.user.has_role("System Manager")) {
			frm.set_value("user", frappe.session.user);
		}

		if (frm.is_new()) {
			frm.dashboard.set_headline(
				__("Save first, then upload the signature image.")
			);
		}
	},

	refresh(frm) {
		render_signature_preview(frm);
	},

	signature_image(frm) {
		render_signature_preview(frm);
	},

	image_width(frm) {
		render_signature_preview(frm);
	},

	image_height(frm) {
		render_signature_preview(frm);
	},
});
