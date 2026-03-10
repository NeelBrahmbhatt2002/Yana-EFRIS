(function () {
	const original_throw = frappe.throw;
	frappe.throw = function (message, title) {
		if (typeof message === "string" && message.includes("Exchange Rate not available")) {
			console.log("🔇 Suppressed ERPNext exchange rate throw:", message);
			return; // skip showing this specific error
		}
		return original_throw.apply(this, arguments);
	};

	const original_msgprint = frappe.msgprint;
	frappe.msgprint = function (message, title, indicator, alert) {
		if (typeof message === "string" && message.includes("Exchange Rate not available")) {
			console.log("🔇 Suppressed ERPNext exchange rate msgprint:", message);
			return;
		}
		return original_msgprint.apply(this, arguments);
	};
})();
frappe.ui.form.on("Purchase Invoice", {
	supplier: function (frm) {
		if (!frm.doc.supplier) return;

		frappe.call({
			method: "yana_efris.api.efris_api.get_supplier_payable_summary",
			args: {
				supplier: frm.doc.supplier,
				company: frm.doc.company,
			},
			callback: function (r) {
				if (!r.message) return;

				let data = r.message;

				frm.set_value("custom_customer_outstanding_amount", data.outstanding);

				frappe.msgprint({
					title: "Supplier Payable Information",
					indicator: data.overdue_count > 0 ? "orange" : "green",
					message: `
                        <b>Outstanding Amount:</b> ${format_currency(data.outstanding)} <br>
                        <b>Overdue Bills:</b> ${data.overdue_count} <br>
                        <b>Oldest Overdue:</b> ${data.oldest_days} days
                    `,
				});
			},
		});
	},
	currency(frm) {
		fetch_and_set_exchange_rate_common(frm);
	},
});
