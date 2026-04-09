// exchange_rate_common.js
// window.fetch_and_set_exchange_rate_common = function (frm) {
// 	if (frm.doc.currency && frm.doc.company) {
// 		frappe.call({
// 			method: "yana_efris.api.efris_api.get_exchange_rate",
// 			args: {
// 				currency: frm.doc.currency,
// 				company_name: frm.doc.company,
// 			},
// 			callback: function (r) {
// 				console.log("Triggering from here");
// 				if (!r.message) return;

// 				let rate = parseFloat(r.message.rate) || null;
// 				if (rate) {
// 					frm.set_value("conversion_rate", rate);
// 					rate !== 1 && frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
// 				}
// 			},
// 		});
// 	}
// };

// exchange_rate_common.js
window.fetch_and_set_exchange_rate_common = function (frm) {
	if (!(frm.doc.currency && frm.doc.company)) return;

	// 🔹 Step 1: Check if company is EFRIS-enabled
	frappe.db.get_value("Company", frm.doc.company, "efris_company").then((r) => {
		const is_efris = r.message?.efris_company;

		// 🔹 Step 2: Only call API if EFRIS company
		if (is_efris) {
			frappe.call({
				method: "yana_efris.api.efris_api.get_exchange_rate",
				args: {
					currency: frm.doc.currency,
					company_name: frm.doc.company,
				},
				callback: function (r) {
					console.log("Triggering from EFRIS");

					if (!r.message) return;

					let rate = parseFloat(r.message.rate) || null;

					if (rate) {
						frm.set_value("conversion_rate", rate);

						if (rate !== 1) {
							frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
						}
					}
				},
				error: (err) => console.error("EFRIS exchange rate error", err),
			});
		} else {
			console.log("Non-EFRIS company → skipping exchange rate API");

			// Optional: fallback logic
			// frm.set_value("conversion_rate", 1);
		}
	});
};
