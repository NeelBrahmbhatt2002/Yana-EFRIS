function fetch_and_set_exchange_rate(frm) {
	if (frm.doc.currency && frm.doc.company) {
		frappe.call({
			method: "yana_efris.api.efris_api.get_exchange_rate",
			args: {
				currency: frm.doc.currency,
				company_name: frm.doc.company,
			},
			callback: function (r) {
				if (!r.message) return;

				if (r.message) {
					let rate = parseFloat(r.message.rate) || null;
					if (rate) {
						frm.set_value("conversion_rate", rate);
						// optional: show success message
						// frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
					}
				}
			},
		});
	}
}

const doctypes_with_exchange_rate = [
	"Quotation",
	"Sales Order",
	"Sales Invoice",
	// "Purchase Order",
	// "Purchase Invoice",
];

doctypes_with_exchange_rate.forEach((doctype) => {
	frappe.ui.form.on(doctype, {
		currency: function (frm) {
			fetch_and_set_exchange_rate(frm);
		},
	});
});
