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

function queue_live_stock_call(frm, row) {
	if (!row.item_code) {
		console.log("[EFRIS] Skipping row, no item code.", row);
		return;
	}

	// Avoid double API calls for the same row
	if (row.__live_stock_fetched) {
		console.log(`[EFRIS] Already fetched → ${row.item_code}`);
		return;
	}

	// Mark row as processed BEFORE API call to avoid repeat triggers
	row.__live_stock_fetched = true;

	console.log(`[EFRIS QUEUE] Added → ${row.item_code}`);

	// Add API call to queue
	efrisQueue = efrisQueue.then(() => {
		console.log(`[EFRIS QUEUE] Processing → ${row.item_code}`);

		return new Promise((resolve) => {
			frappe.call({
				method: "yana_efris.api.efris_api.fetch_live_stock_by_goods_code",
				args: {
					goods_code: row.item_code,
					company: frm.doc.company,
				},
				callback(r) {
					console.log(`[EFRIS] API Response for ${row.item_code}:`, r);

					if (r.message?.success) {
						frappe.model.set_value(
							row.doctype,
							row.name,
							"custom_efris_live_stock",
							r.message.live_stock,
						);

						frappe.show_alert({
							message: `EFIRS Live Stock (${row.item_code}): <b>${r.message.live_stock}</b>`,
							indicator: "green",
						});
					} else {
						console.error(`[EFRIS] Failed for ${row.item_code}:`, r.message);
						frappe.show_alert({
							message: `EFRIS fetch failed (${row.item_code}): ${r.message.message}`,
							indicator: "red",
						});
					}

					resolve(); // Move queue to next request
				},

				error(err) {
					console.error(`[EFRIS] Network/API Error for ${row.item_code}:`, err);
					resolve(); // Continue queue even on error
				},
			});
		});
	});
}

function toggle_efris_stock_column(frm) {
	if (!frm.doc.company) return;

	frappe.db.get_value("Company", frm.doc.company, "efris_company").then((r) => {
		const is_efris = r.message?.efris_company;
		console.log("Is EFRIS Company?", is_efris);

		let grid = frm.fields_dict["items"].grid;

		// 🔹 Update property
		grid.update_docfield_property("custom_efris_live_stock", "hidden", is_efris ? 0 : 1);

		// 🔥 IMPORTANT: Force re-render
		grid.reset_grid();
		frm.refresh_field("items");
	});
}

function update_items_label(frm) {
	let note = frm.doc.custom_note || "";
	let label = note ? `Items (${note})` : "Items";

	const controlLabel = frm.fields_dict.items.wrapper
		.closest(".frappe-control")
		?.querySelector(".control-label");

	if (controlLabel) {
		controlLabel.textContent = label;
	}
}

function update_delivery_status(frm) {
	frm.doc.items.forEach((row) => {
		const qty = flt(row.qty);
		const delivered = flt(row.delivered_qty);

		if (delivered <= 0) {
			row.custom_delivery_status = "❌ Not Delivered";
		} else if (delivered < qty) {
			row.custom_delivery_status = "🟡 Partially Delivered";
		} else {
			row.custom_delivery_status = "✅ Delivered";
		}
	});

	frm.refresh_field("items");
}

frappe.ui.form.on("Sales Order", {
	onload(frm) {
		toggle_efris_stock_column(frm);
		update_items_label(frm);
	},

	company(frm) {
		toggle_efris_stock_column(frm);
		update_items_label(frm);
	},
	refresh(frm) {
		toggle_efris_stock_column(frm);
		update_delivery_status(frm);
		update_items_label(frm);

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
	onload_post_render(frm) {
		update_delivery_status(frm);
	},

	customer: function (frm) {
		if (!frm.doc.customer) return;

		frappe.call({
			method: "yana_efris.api.efris_api.get_customer_credit_summary",
			args: {
				customer: frm.doc.customer,
				company: frm.doc.company,
			},
			callback: function (r) {
				if (!r.message) return;

				let data = r.message;

				frm.set_value("custom_outstanding_amount", data.outstanding);

				frappe.msgprint({
					title: "Customer Credit Information",
					indicator: data.overdue_count > 0 ? "red" : "green",
					message: `
                        <b>Outstanding Amount:</b> ${format_currency(data.outstanding)} <br>
                        <b>Overdue Invoices:</b> ${data.overdue_count} <br>
                        <b>Oldest Overdue:</b> ${data.oldest_days} days
                    `,
				});
			},
		});
	},
	currency(frm) {
		// if (frm.doc.currency && frm.doc.company) {
		// 	frappe.call({
		// 		method: "yana_efris.api.efris_api.get_exchange_rate",
		// 		args: {
		// 			currency: frm.doc.currency,
		// 			company_name: frm.doc.company,
		// 		},
		// 		callback: function (r) {
		// 			// console.log("Response is", r);
		// 			if (!r.message) return;

		// 			if (r.message) {
		// 				let rate = parseFloat(r.message.rate) || null;
		// 				if (rate) {
		// 					frm.set_value("conversion_rate", rate);

		// 					rate !== 1 && frappe.msgprint(`Exchange Rate from EFRIS: ${rate}`);
		// 				}
		// 			}
		// 		},
		// 	});
		// }
		fetch_and_set_exchange_rate_common(frm);
	},
});

frappe.ui.form.on("Sales Order Item", {
	item_code: function (frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.item_code || !frm.doc.company) return;

		// 🔹 Step 1: Check if company is EFRIS
		frappe.db.get_value("Company", frm.doc.company, "efris_company").then((r) => {
			const is_efris = r.message?.efris_company;

			// ❌ Skip if not EFRIS
			if (!is_efris) {
				console.log("Non-EFRIS company → skipping stock API");

				// Optional: clear field
				frappe.model.set_value(cdt, cdn, "custom_efris_live_stock", null);

				return;
			}

			// ✅ Step 2: Call API
			frappe.db
				.get_value("Item", row.item_code, ["item_code", "item_group"])
				.then((item_res) => {
					const actual_item_code = item_res.message.item_code;
					const item_group = item_res.message.item_group;

					// Show notification for Service Items
					if (item_group && item_group.toLowerCase() === "services") {
						frappe.show_alert({
							message: __("This is a Service Item"),
							indicator: "orange",
						});
					}

					frappe.call({
						method: "yana_efris.api.efris_api.fetch_live_stock_by_goods_code",
						args: {
							goods_code: actual_item_code,
							company: frm.doc.company,
						},
						callback: function (r) {
							if (!r.message) return;

							console.log("Stock Quantity", r);

							if (r.message.success) {
								const stock = r.message.live_stock;
								const item_id = r.message.efris_item_id;

								frappe.model.set_value(cdt, cdn, "custom_efris_live_stock", stock);

								if (stock <= 0) {
									frappe.show_alert({
										message: __(
											`Live EFRIS stock for ${row.item_code}: <b>${stock}</b>`,
										),
										indicator: "red",
									});
								} else {
									frappe.show_alert({
										message: __(
											`Live EFRIS stock for ${row.item_code}: <b>${stock}</b>`,
										),
										indicator: "green",
									});
								}

								// frappe.show_alert({
								// 	message: `Live EFRIS stock for ${row.item_code}: <b>${stock}</b>`,
								// 	indicator: "green",
								// });

								console.log(`EFRIS ID stored: ${item_id}`);
							} else {
								frappe.show_alert({
									message: `EFRIS stock fetch failed: ${r.message.message || "Error"}`,
									indicator: "red",
								});
							}
						},
						error: (err) => console.error("EFRIS stock API error", err),
					});
				});
		});
	},
});
