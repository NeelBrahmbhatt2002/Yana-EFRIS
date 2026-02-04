# Copyright (c) 2026, YanaERP and contributors
# For license information, please see license.txt

# import frappe


# def execute(filters=None):
# 	columns, data = [], []
# 	return columns, data

import frappe
from frappe import _
from frappe.utils import cint
from frappe.defaults import get_user_default


def execute(filters=None):
	frappe.log_error(
        f"Custom Report code running",
        "Custom Report"
    )
	if not filters:
		filters = {}

	days_since_last_order = cint(filters.get("days_since_last_order", 60))
	doctype = filters.get("doctype", "Sales Invoice")

	if days_since_last_order < 0:
		frappe.throw(_("'Days Since Last Order' must be >= 0"))

	company = get_user_default("Company")
	if not company:
		frappe.throw(_("Company is not set for the current user"))

	columns = get_columns()
	data = get_data(company, days_since_last_order, doctype)

	return columns, data


def get_data(company, days, doctype):
	date_field = "posting_date" if doctype == "Sales Invoice" else "transaction_date"

	return frappe.db.sql(
		f"""
		SELECT
			c.name AS customer,
			c.customer_name,
			c.territory,
			c.customer_group,
			COUNT(t.name) AS number_of_orders,
			SUM(t.base_net_total) AS total_order_value,
			MAX(t.base_net_total) AS last_order_amount,
			MAX(t.{date_field}) AS last_order_date,
			DATEDIFF(CURDATE(), MAX(t.{date_field})) AS days_since_last_order
		FROM `tabCustomer` c
		JOIN `tab{doctype}` t ON t.customer = c.name
		WHERE
			t.docstatus = 1
			AND t.company = %(company)s
		GROUP BY c.name
		HAVING DATEDIFF(CURDATE(), MAX(t.{date_field})) >= %(days)s
		ORDER BY days_since_last_order DESC
		""",
		{
			"company": company,
			"days": days,
		},
		as_list=1,
	)


def get_columns():
	return [
		_("Customer") + ":Link/Customer:120",
		_("Customer Name") + ":Data:120",
		_("Territory") + "::120",
		_("Customer Group") + "::120",
		_("Number of Order") + ":Int:120",
		_("Total Order Value") + ":Currency:120",
		_("Last Order Amount") + ":Currency:160",
		_("Last Order Date") + ":Date:160",
		_("Days Since Last Order") + ":Int:160",
	]
