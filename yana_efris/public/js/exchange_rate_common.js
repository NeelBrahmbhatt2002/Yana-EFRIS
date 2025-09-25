// exchange_rate_common.js

// exchange_rate_common.js
window.fetch_and_set_exchange_rate_common = function (frm) {
	if (frm.doc.currency && frm.doc.company) {
		frappe.call({
			method: "yana_efris.api.efris_api.get_exchange_rate",
			args: {
				currency: frm.doc.currency,
				company_name: frm.doc.company,
			},
			callback: function (r) {
				if (!r.message) return;

				let rate = parseFloat(r.message.rate) || null;
				if (rate) {
					frm.set_value("conversion_rate", rate);
					rate !== 1 && frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
				}
			},
		});
	}
};
