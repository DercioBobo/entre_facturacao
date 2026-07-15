import frappe


def get_user_signature(user):
	if not frappe.db.get_single_value("Facturacao Settings", "enable_signature_on_print"):
		return None
	return frappe.db.get_value("User Signature", {"user": user}, "signature_image")
