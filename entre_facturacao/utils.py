import frappe

DEFAULT_SIGNATURE_WIDTH = 150
DEFAULT_SIGNATURE_HEIGHT = 60


def get_user_signature(user):
	if not frappe.db.get_single_value("Facturacao Settings", "enable_signature_on_print"):
		return None
	return frappe.db.get_value("User Signature", {"user": user}, "signature_image")


def get_user_signature_details(user):
	if not frappe.db.get_single_value("Facturacao Settings", "enable_signature_on_print"):
		return None

	row = frappe.db.get_value(
		"User Signature",
		{"user": user},
		["signature_image", "signature_name", "cargo", "image_width", "image_height"],
		as_dict=True,
	)
	if not row:
		return None

	return {
		"image": row.signature_image,
		"name": row.signature_name,
		"cargo": row.cargo,
		"width": row.image_width or DEFAULT_SIGNATURE_WIDTH,
		"height": row.image_height or DEFAULT_SIGNATURE_HEIGHT,
	}
