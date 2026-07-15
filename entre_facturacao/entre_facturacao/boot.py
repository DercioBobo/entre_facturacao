import frappe


def boot_session(bootinfo):
	bootinfo.entre_facturacao_settings = {
		"enable_signature_on_print": frappe.db.get_single_value(
			"Facturacao Settings", "enable_signature_on_print"
		)
	}
