// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Balance Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			width: "80",
			options: "Company",
			default: frappe.defaults.get_default("company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			width: "80",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			width: "80",
			options: "Item Group",
		},
		{
			fieldname: "item_code",
			label: __("Items"),
			fieldtype: "MultiSelectList",
			width: "80",
			options: "Item",
			get_data: async function (txt) {
				let item_group = frappe.query_report.get_filter_value("item_group");

				let filters = {
					...(item_group && { item_group }),
					is_stock_item: 1,
				};

				let { message: data } = await frappe.call({
					method: "erpnext.controllers.queries.item_query",
					args: {
						doctype: "Item",
						txt: txt,
						searchfield: "name",
						start: 0,
						page_len: 10,
						filters: filters,
						as_dict: 1,
					},
				});

				data = data.map(({ name, ...rest }) => {
					return {
						value: name,
						description: Object.values(rest),
					};
				});

				return data || [];
			},
		},
		{
			fieldname: "warehouse",
			label: __("Warehouses"),
			fieldtype: "MultiSelectList",
			width: "80",
			options: "Warehouse",
			get_data: (txt) => {
				let warehouse_type = frappe.query_report.get_filter_value("warehouse_type");
				let company = frappe.query_report.get_filter_value("company");

				let filters = {
					...(warehouse_type && { warehouse_type }),
					...(company && { company }),
				};

				return frappe.db.get_link_options("Warehouse", txt, filters);
			},
		},
		{
			fieldname: "warehouse_type",
			label: __("Warehouse Type"),
			fieldtype: "Link",
			width: "80",
			options: "Warehouse Type",
		},
		{
			fieldname: "valuation_field_type",
			label: __("Valuation Field Type"),
			fieldtype: "Select",
			width: "80",
			options: "Currency\nFloat",
			default: "Currency",
		},
		{
			fieldname: "include_uom",
			label: __("Include UOM"),
			fieldtype: "Link",
			options: "UOM",
		},
		{
			fieldname: "show_variant_attributes",
			label: __("Show Variant Attributes"),
			fieldtype: "Check",
		},
		{
			fieldname: "show_stock_ageing_data",
			label: __("Show Stock Ageing Data"),
			fieldtype: "Check",
		},
		{
			fieldname: "ignore_closing_balance",
			label: __("Ignore Closing Balance"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "include_zero_stock_items",
			label: __("Include Zero Stock Items"),
			fieldtype: "Check",
			default: 0,
		},
		{
			fieldname: "show_dimension_wise_stock",
			label: __("Show Dimension Wise Stock"),
			fieldtype: "Check",
			default: 0,
		},
	],

	// formatter: function (value, row, column, data, default_formatter) {
	// 	value = default_formatter(value, row, column, data);

	// 	if (column.fieldname == "out_qty" && data && data.out_qty > 0) {
	// 		value = "<span style='color:red'>" + value + "</span>";
	// 	} else if (column.fieldname == "in_qty" && data && data.in_qty > 0) {
	// 		value = "<span style='color:green'>" + value + "</span>";
	// 	}

	// 	return value;
	// },

	formatter: function (value, row, column, data, default_formatter) {
		// Header cells have no data
		if (!data) {
			return default_formatter(value, row, column, data);
		}

		const integer_fields = [
			"bal_qty",
			"opening_qty",
			"in_qty",
			"out_qty",
			"reserved_stock",
			"in_val",
			"out_val",
			"val_rate",
		];

		if (integer_fields.includes(column.fieldname)) {
			value = Math.round(data[column.fieldname]).toLocaleString();
		} else {
			value = default_formatter(value, row, column, data);
		}

		if (column.fieldname === "out_qty" && data.out_qty > 0) {
			value = `<span style="color:red">${value}</span>`;
		} else if (column.fieldname === "in_qty" && data.in_qty > 0) {
			value = `<span style="color:green">${value}</span>`;
		}

		return value;
	},
	get_datatable_options(options) {
		console.log("get_datatable_options called");

		options.hooks = options.hooks || {};

		options.hooks.columnTotal = function (values, cell) {
			console.log("columnTotal called", cell.column.id, values);
			return null;
		};

		console.log(options);

		return options;
	},
	onload: function (report) {
		report.page.add_inner_button(__("View Stock Ledger"), function () {
			var filters = report.get_values();
			frappe.set_route("query-report", "Stock Ledger", filters);
		});

		const hide_qty_totals = () => {
			console.log("hide_qty_totals");
			const totalRow = document.querySelector(".dt-row-totalRow");
			if (!totalRow) return;

			const qtyFields = ["bal_qty", "opening_qty", "in_qty", "out_qty", "reserved_stock"];

			const cells = totalRow.querySelectorAll(".dt-cell");

			frappe.query_report.columns.forEach((column, index) => {
				console.log(column.fieldname, index);
				if (qtyFields.includes(column.fieldname)) {
					// +1 because the total row has an extra serial-number cell
					const cell = cells[index + 1];

					if (cell) {
						const content = cell.querySelector(".dt-cell__content");
						if (content) {
							content.style.visibility = "hidden";
						} else {
							cell.style.visibility = "hidden";
						}
					}
				}
			});
		};

		// Initial load
		setTimeout(hide_qty_totals, 100);

		// Every report refresh (filters, reload, etc.)
		const original_refresh = report.refresh.bind(report);

		report.refresh = function () {
			original_refresh();

			setTimeout(hide_qty_totals, 100);
		};
	},
};

erpnext.utils.add_inventory_dimensions("Stock Balance Report", 8);
