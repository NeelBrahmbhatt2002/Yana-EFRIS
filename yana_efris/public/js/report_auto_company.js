frappe.provide("yana_efris.stock_projected_qty");

yana_efris.stock_projected_qty.apply_company_default = function () {
	const report = frappe.query_reports["Stock Projected Qty"];
	if (!report || !report.filters) return;

	report.filters.forEach((f) => {
		if (f.fieldname === "company") {
			f.default = "MERCIA HOSPITALITY SOLUTIONS LIMITED";
		}
	});
};

// run patch after report loads
frappe.after_ajax(() => {
	if (frappe.query_report?.report_name === "Stock Projected Qty") {
		yana_efris.stock_projected_qty.apply_company_default();
	}
});
