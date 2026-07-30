frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.is_new()) return;

		let attempts = 0;

		let timer = setInterval(() => {
			attempts++;

			// Stop after 2 seconds
			if (attempts > 20) {
				clearInterval(timer);
				return;
			}

			// Wait until the menu exists
			if (!frm.page.wrapper.find(".menu-btn-group").length) {
				return;
			}

			clearInterval(timer);

			// Remove previous PDF item if it already exists
			frm.page.wrapper.find(".custom-pdf-menu-item").remove();

			frm.page.add_menu_item(__("PDF"), function () {
				let format = frm.meta.default_print_format || "Standard";

				let url =
					`/api/method/yana_efris.api.efris_api.download_invoice_pdf` +
					`?doctype=${encodeURIComponent(frm.doctype)}` +
					`&name=${encodeURIComponent(frm.doc.name)}` +
					`&format=${encodeURIComponent(format)}`;

				let a = document.createElement("a");
				a.href = url;
				a.download = `${frm.doc.name}.pdf`;
				document.body.appendChild(a);
				a.click();
				document.body.removeChild(a);
			});

			// Mark the item so we can remove it next refresh
			frm.page.wrapper.find(".dropdown-menu li:last").addClass("custom-pdf-menu-item");
		}, 100);
	},
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
						const data = r.message;

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

							// Fetch UOM from Item Master (THIS IS THE KEY PART)
							frappe.call({
								method: "frappe.client.get_value",
								args: {
									doctype: "Item",
									filters: { name: g.itemCode },
									fieldname: ["stock_uom"],
								},
								async: false,
								callback: function (res) {
									if (res.message) {
										child.uom = res.message.stock_uom;
										child.stock_uom = res.message.stock_uom;
										frm.refresh_field("items");
									}
								},
							});
						});

						// 5. Refresh again AFTER adding items
						frm.refresh_field("items");

						frm.refresh();

						frappe.msgprint({
							title: "EFRIS Response",
							indicator: "blue",
							message: __(
								"Invoice fetched successfully and mapped items automatically.",
							),
						});
					}
				},
			});
		}
	},
});
