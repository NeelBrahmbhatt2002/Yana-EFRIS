// Copyright (c) 2026, YanaERP and contributors
// For license information, please see license.txt

// frappe.query_reports["Inactive Customers by Company"] = {
// 	"filters": [

// 	]
// };

frappe.query_reports["Inactive Customers by Company"] = {
	filters: [
		{
			fieldname: "days_since_last_order",
			label: "Days Since Last Order",
			fieldtype: "Int",
			default: 60,
			reqd: 1,
		},
		{
			fieldname: "doctype",
			label: "Based On",
			fieldtype: "Select",
			options: ["Sales Invoice", "Sales Order"],
			default: "Sales Invoice",
		},
	],
};
