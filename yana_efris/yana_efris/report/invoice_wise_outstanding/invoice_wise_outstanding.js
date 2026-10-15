// Copyright (c) 2026, YanaERP and contributors
// For license information, please see license.txt

// frappe.query_reports["Invoice-wise Outstanding"] = {
// 	"filters": [

// 	]
// };

frappe.query_reports["Invoice-wise Outstanding"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "as_on_date",
			label: __("As of Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "from_date",
			label: __("Invoice From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Invoice To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "currency",
			label: __("Invoice Currency"),
			fieldtype: "Link",
			options: "Currency",
		},
	],
};
