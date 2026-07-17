app_name = "entre_facturacao"
app_title = "Entre Facturacao"
app_publisher = "Dércio Bobo"
app_description = "Custom pages, reports, and fields for ERPNext Sales Invoice"
app_email = "derciobob@gmail.com"
app_license = "MIT"
required_apps = ["frappe", "erpnext"]

# app_include_css = "/assets/entre_facturacao/css/entre_facturacao.css"
# app_include_js = "/assets/entre_facturacao/js/entre_facturacao.js"

extend_bootinfo = "entre_facturacao.boot.boot_session"

jinja = {
    "methods": [
        "entre_facturacao.utils.get_user_signature",
    ],
}

permission_query_conditions = {
    "User Signature": "entre_facturacao.entre_facturacao.doctype.user_signature.user_signature.get_permission_query_conditions",
}

has_permission = {
    "User Signature": "entre_facturacao.entre_facturacao.doctype.user_signature.user_signature.has_permission",
}

fixtures = [
    {
        "doctype": "Custom Field",
        "filters": [
            ["dt", "=", "Sales Invoice"],
            ["fieldname", "in", ["custom_signature_section", "custom_print_signature"]],
        ],
    },
]

# doc_events = {}

# scheduler_events = {}
