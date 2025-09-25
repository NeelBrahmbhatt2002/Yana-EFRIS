app_name = "yana_efris"
app_title = "Yana EFRIS"
app_publisher = "YanaERP"
app_description = "App for implementing EFRIS of Uganda Revenue Authority"
app_email = "admin@yanaerp.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

doctype_js = {
    "Quotation": "public/js/quotation.js",        # you can add more doctypes
    "Sales Order": "public/js/sales_order.js",
    "Sales Invoice": "public/js/sales_invoice.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Invoice": "public/js/purchase_invoice.js"
}

app_include_js = [
    "/assets/yana_efris/js/exchange_rate_common.js"
]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "yana_efris",
# 		"logo": "/assets/yana_efris/logo.png",
# 		"title": "Yana EFRIS",
# 		"route": "/yana_efris",
# 		"has_permission": "yana_efris.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/yana_efris/css/yana_efris.css"
# app_include_js = "/assets/yana_efris/js/yana_efris.js"
# app_include_js = [
#     "/assets/yana_efris/js/exchange_rate.js"
# ]


# include js, css files in header of web template
# web_include_css = "/assets/yana_efris/css/yana_efris.css"
# web_include_js = "/assets/yana_efris/js/yana_efris.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "yana_efris/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "yana_efris/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "yana_efris.utils.jinja_methods",
# 	"filters": "yana_efris.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "yana_efris.install.before_install"
# after_install = "yana_efris.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "yana_efris.uninstall.before_uninstall"
# after_uninstall = "yana_efris.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "yana_efris.utils.before_app_install"
# after_app_install = "yana_efris.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "yana_efris.utils.before_app_uninstall"
# after_app_uninstall = "yana_efris.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "yana_efris.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"yana_efris.tasks.all"
# 	],
# 	"daily": [
# 		"yana_efris.tasks.daily"
# 	],
# 	"hourly": [
# 		"yana_efris.tasks.hourly"
# 	],
# 	"weekly": [
# 		"yana_efris.tasks.weekly"
# 	],
# 	"monthly": [
# 		"yana_efris.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "yana_efris.install.before_tests"

# Overriding Methods
# ------------------------------
#

# override_whitelisted_methods = {
#     "erpnext.setup.utils.get_exchange_rate": "yana_efris.api.efris_api.get_exchange_rate"
# }

#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "yana_efris.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["yana_efris.utils.before_request"]
# after_request = ["yana_efris.utils.after_request"]

# Job Events
# ----------
# before_job = ["yana_efris.utils.before_job"]
# after_job = ["yana_efris.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"yana_efris.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

