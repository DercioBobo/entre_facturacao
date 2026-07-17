import frappe
from frappe import _
from frappe.model.document import Document


class UserSignature(Document):
	def validate(self):
		if self.user != frappe.session.user and "System Manager" not in frappe.get_roles():
			frappe.throw(_("You can only manage your own signature."))


def get_permission_query_conditions(user=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return ""
	return f"`tabUser Signature`.`user` = {frappe.db.escape(user)}"


def has_permission(doc, user=None, permission_type=None):
	user = user or frappe.session.user
	if "System Manager" in frappe.get_roles(user):
		return True
	return doc.user == user
