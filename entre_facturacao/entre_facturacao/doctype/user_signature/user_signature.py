import frappe
from frappe import _
from frappe.model.document import Document


class UserSignature(Document):
	def validate(self):
		if self.user != frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(_("You can only manage your own signature."))

		if self.image_width is not None and self.image_width <= 0:
			frappe.throw(_("Width must be greater than 0."))
		if self.image_height is not None and self.image_height <= 0:
			frappe.throw(_("Height must be greater than 0."))


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	return f"`tabUser Signature`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True

	if isinstance(doc, str):
		if not frappe.db.exists("User Signature", doc):
			# Doc not yet inserted (e.g. attaching the signature image before
			# first save uses the temporary "new-..." name). Nothing to
			# protect yet; validate() enforces ownership on insert.
			return True
		doc = frappe.get_doc("User Signature", doc)

	if not doc.user:
		# Blank/unsaved document (e.g. frappe.new_doc() used internally to
		# check "create" permission during file attach). Nothing to protect
		# yet; validate() enforces ownership on insert.
		return True

	return doc.user == user
