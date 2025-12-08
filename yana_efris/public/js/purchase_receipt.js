frappe.ui.form.on("Purchase Receipt", {
	custom_fdn_number(frm) {
		const fdn = frm.doc.custom_fdn_number;

		if (fdn && fdn.length === 13) {
			console.log("FDN Number", fdn);
			frappe.call({
				method: "yana_efris.api.efris_api.validate_fdn_number",
				args: {
					fdn_number: fdn,
					company: frm.doc.company,
				},
				freeze: true,
				freeze_message: "Fetching invoice from EFRIS...",
				callback: function (r) {
					if (!r.exc) {
						console.log("RAW T108 Response:", r.message);

						const data = r.message;
						console.log("Actual Response", data);

						// 3. Clear existing items properly
						frm.doc.items = []; // Hard reset (more reliable)
						frm.refresh_field("items");

						// 4. Add new item rows
						data.goods.forEach((g) => {
							let child = frm.add_child("items");
							child.item_code = g.itemCode;
							child.item_name = g.item;
							child.qty = parseFloat(g.qty);
							child.rate = parseFloat(g.unitPrice);
							child.amount = parseFloat(g.total);
						});

						// 5. Refresh again AFTER adding items
						frm.refresh_field("items");

						frm.refresh();

						frappe.msgprint({
							title: "EFRIS Response",
							indicator: "blue",
							message: __(
								"Invoice fetched successfully. Check console for full response."
							),
						});
					}
				},
			});
		}
	},
});
