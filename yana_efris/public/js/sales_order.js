// Suppress ERPNext default "exchange rate not available" error
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

frappe.ui.form.on("Sales Order", {
	currency(frm) {
		if (frm.doc.currency && frm.doc.company) {
			frappe.call({
				method: "yana_efris.api.efris_api.get_exchange_rate",
				args: {
					currency: frm.doc.currency,
					company_name: frm.doc.company,
				},
				callback: function (r) {
					// console.log("Response is", r);
					if (!r.message) return;

					if (r.message) {
						let rate = parseFloat(r.message.rate) || null;
						if (rate) {
							frm.set_value("conversion_rate", rate);

							rate !== 1 && frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
						}
					}
				},
			});
		}
	},
});
