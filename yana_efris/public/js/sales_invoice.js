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

// Global EFRIS sequential queue
let efrisQueue = Promise.resolve();

// ---------------------------------------------------------
// Queue-based API call (ENSURES ONLY ONE REQUEST AT A TIME)
// ---------------------------------------------------------

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
							r.message.live_stock
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

frappe.ui.form.on("Sales Invoice", {
	company(frm) {
		if (frm.doc.company) {
			frappe.call({
				method: "yana_efris.api.efris_api.fetch_efris_branches",
				args: {
					company_name: frm.doc.company,
				},
				// callback: (r) => console.log("frappe.call ok", r),
				error: (err) => console.error("frappe.call err", err),
			});
		}
	},
	currency(frm) {
		fetch_and_set_exchange_rate_common(frm);
	},

	custom_new_customer_tin: function (frm) {
		const tin = frm.doc.custom_new_customer_tin;

		// Basic validation: 10 digits
		if (!tin || tin.length !== 10 || !/^\d{10}$/.test(tin)) {
			return;
		}

		if (!frm.doc.custom_is_new_customer) {
			frappe.db.get_value("Customer", { tax_id: tin }, "name").then((r) => {
				if (r && r.message && r.message.name) {
					frm.set_value("customer", r.message.name);
				}
			});
			return;
		}
		frappe.db.get_value("Customer", { tax_id: tin }, "name").then((r) => {
			if (r?.message?.name) {
				frm.set_value("customer", r.message.name);
				frappe.msgprint("Customer already exists!");
				return;
			} else {
				// ✅ Safe to call API here (only when customer doesn’t exist)
				const e_company_name = frm.doc.company;
				const ninBrn = "";

				// Fetch Current User email
				var Current_User = frappe.session.user;
				var user_email = "";
				frappe.call({
					method: "frappe.client.get",
					args: {
						doctype: "User",
						filters: { email: Current_User },
					},
					callback: function (r) {
						user_email = r?.message?.name || "";
						// Fetch Customer Details From EFRIS
						if (user_email) {
							frappe.call({
								method: "yana_efris.api.efris_api.query_customer_details",
								args: {
									doc: frm.doc.name, // ✅ doc_name instead of doc
									e_company_name,
									tax_id: tin,
									ninBrn,
									accountManager: user_email,
								},
								freeze: true,
								freeze_message: __("Fetching customer details from EFRIS..."),
								callback: function (r) {
									if (r.message) {
										frm.set_value("customer", r.message.customer_id);
										frappe.msgprint("Customer details fetched successfully!");
									}
								},
								error: function (err) {
									console.error("❌ API Error:", err);
									frappe.msgprint(
										"Failed to fetch customer details from EFRIS."
									);
								},
							});
						}
					},
				});
			}
		});
	},

	custom_is_new_customer: function (frm) {
		frm.set_value("custom_new_customer_tin", "");
	},
});

frappe.ui.form.on("Sales Invoice", {
	refresh(frm) {
		console.log("[EFRIS] refresh() triggered");

		// Skip EFRIS calls when opening an old Sales Invoice
		if (!frm.is_new() || frm.doc.docstatus !== 0) {
			console.log("[EFRIS] Existing/Submitted Sales Invoice → No API calls.");
			return;
		}

		if (!frm.doc.items || frm.doc.items.length === 0) {
			console.log("[EFRIS] No items in the table.");
			return;
		}

		// Scan all rows → process only rows not yet fetched
		frm.doc.items.forEach((row) => {
			if (!row.__live_stock_fetched) {
				console.log("[EFRIS] New row detected →", row.item_code);
				queue_live_stock_call(frm, row);
			}
		});
	},
});

frappe.ui.form.on("Sales Invoice Item", {
	item_code: function (frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.item_code) return;

		frappe.call({
			method: "yana_efris.api.efris_api.fetch_live_stock_by_goods_code",
			args: {
				goods_code: row.item_code,
				company: frm.doc.company,
			},
			callback: function (r) {
				if (!r.message) return;
				console.log("Stock Quantity", r);

				if (r.message.success) {
					const stock = r.message.live_stock;
					const item_id = r.message.efris_item_id;

					frappe.model.set_value(cdt, cdn, "custom_efris_live_stock", stock);

					frappe.show_alert({
						message: `Live EFRIS stock for ${row.item_code}: <b>${stock}</b>`,
						indicator: "green",
					});

					console.log(`EFRIS ID stored: ${item_id}`);
				} else {
					frappe.show_alert({
						message: `EFRIS stock fetch failed: ${r.message.message || "Error"}`,
						indicator: "red",
					});
				}
			},
		});
	},
});
