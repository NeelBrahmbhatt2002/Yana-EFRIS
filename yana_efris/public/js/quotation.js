frappe.ui.form.on("Quotation", {
	currency(frm) {
		if (frm.doc.currency && frm.doc.company) {
			frappe.call({
				method: "yana_efris.api.efris_api.get_exchange_rate",
				args: {
					currency: frm.doc.currency,
					company_name: frm.doc.company,
				},
				callback: function (r) {
					console.log("Response is", r);
					if (!r.message) return;

					if (r.message.success) {
						let rate = parseFloat(r.message.rate) || null;
						if (rate) {
							frm.set_value("conversion_rate", rate);
							frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
						}
					} else {
						frappe.msgprint(r.message.message || "Failed to fetch exchange rate.");
					}
				},
			});
		}
	},
});
