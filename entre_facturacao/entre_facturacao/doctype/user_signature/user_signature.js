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
});
