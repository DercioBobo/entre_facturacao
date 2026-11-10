from frappe.model.document import Document

from entre_facturacao import features


class FacturacaoSettings(Document):
	def on_update(self):
		features.sync_workspace()
