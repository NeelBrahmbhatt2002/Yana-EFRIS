// Copyright (c) 2026, YanaERP and contributors
// For license information, please see license.txt

// frappe.query_reports["Sales Performance Report"] = {
// 	"filters": [

// 	]
// };

frappe.query_reports["Sales Performance Report"] = {
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// Bold grand total
		if (column.label.includes("Grand Total")) {
			value = `<strong>${value}</strong>`;
		}

		// Highlight Growth columns
		if (column.label.includes("Growth")) {
			if (data[column.fieldname] < 0) {
				value = `<span style="color:red">${value}</span>`;
			} else {
				value = `<span style="color:green">${value}</span>`;
			}
		}

		// Highlight Var %
		if (column.label.includes("Var")) {
			if (data[column.fieldname] < 0) {
				value = `<span style="color:red">${value}</span>`;
			} else {
				value = `<span style="color:green">${value}</span>`;
			}
		}

		return value;
	},
	filters: [
		{
			fieldname: "sales_person",
			label: "Sales Person",
			fieldtype: "Link",
			options: "Sales Person",
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: "From Date",
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_start(),
		},
		{
			fieldname: "to_date",
			label: "To Date",
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.month_end(),
		},
	],
};
