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
// FINAL OVERRIDE FOR UGANDA FUNCTION
// ---------------------------------------------------------

// setTimeout(() => {
// 	if (typeof set_efris_invoice_details === "function") {
// 		console.log("✅ Overriding Uganda set_efris_invoice_details");

// 		const original_fn = set_efris_invoice_details;

// 		set_efris_invoice_details = async function (frm) {
// 			console.log("🛠 Intercepted Uganda tax logic");

// 			// Run their original function first
// 			await original_fn(frm);

// 			// 🔥 FORCE FIX AFTER their logic
// 			(frm.doc.taxes || []).forEach((tax) => {
// 				if (tax.account_head && tax.account_head.includes("VAT")) {
// 					tax.included_in_print_rate = 1;
// 				}
// 			});

// 			frm.refresh_field("taxes");
// 		};
// 	} else {
// 		console.warn("❌ set_efris_invoice_details not found");
// 	}
// }, 1000); // wait for all scripts to load
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

function get_auto_send_submitted_invoice_flag(frm) {
	console.log("Checking EFRIS company settings for auto send submitted invoice flag");
	return new Promise((resolve) => {
		if (!frm.doc.efris_company || frm.doc.efris_invoice !== 1) {
			return resolve(0);
		}

		frappe.call({
			method: "uganda_compliance.efris.doctype.e_invoicing_settings.e_invoicing_settings.get_e_company_settings",
			args: { company_name: frm.doc.company },
			callback: function (r) {
				if (r.message && r.message.auto_send_submitted_invoice == 1) {
					console.log("Auto send submitted invoice is enabled in EFRIS settings");
					resolve(1);
				} else {
					resolve(0);
				}
			},
		});
	});
}

frappe.ui.form.on("Sales Invoice", {
	// after_submit(frm) {
	// 	setTimeout(() => {
	// 		if (
	// 			frm.doc.custom_sal_invoice_name &&
	// 			frm.doc.name !== frm.doc.custom_sal_invoice_name
	// 		) {
	// 			console.log("After save name", frm.doc.custom_sal_invoice_name);
	// 			frappe.set_route("Form", "Sales Invoice", frm.doc.custom_sal_invoice_name);
	// 		}
	// 	}, 2000);
	// },
	refresh: async function (frm) {
		// Give Uganda Compliance time to add its button
		setTimeout(async () => {
			// Remove original Uganda Compliance button
			frm.remove_custom_button(__("Submit To EFRIS"));

			// Same conditions as Uganda Compliance
			if (
				frm.doc.docstatus != 1 ||
				!frm.doc.efris_company ||
				frm.doc.efris_irn ||
				!frm.doc.efris_invoice
			) {
				console.log("Skipping EFRIS submission button for non-EFRIS or return invoices");
				return;
			}

			const auto_send_submitted_invoice = await get_auto_send_submitted_invoice_flag(frm);
			console.log("Auto send submitted invoice flag:", auto_send_submitted_invoice);

			if (auto_send_submitted_invoice != 1) {
				// Add our custom button
				console.log("Adding custom EFRIS button");
				frm.add_custom_button(__("Submit To EFRIS"), async function () {
					frappe.confirm(
						__("Are you sure you want to submit?"),
						async function () {
							try {
								const response = await frappe.call({
									method: "yana_efris.api.efris_api.send_to_efris",
									args: {
										doc: frm.doc,
									},
									freeze: true,
									freeze_message: __("Submitting to EFRIS..."),
								});

								if (response.message) {
									frappe.msgprint(
										__("Sales Invoice submitted to EFRIS successfully."),
									);

									console.log("Full Response:", response);
									console.log("Response Message:", response.message);

									if (response.message.new_name) {
										frappe.set_route(
											"Form",
											"Sales Invoice",
											response.message.new_name,
										);
									} else {
										frm.reload_doc();
									}

									// For now just reload.
									// Later we will redirect to SAL series.
								} else {
									frm.reload_doc();
									frappe.msgprint(
										__("Failed to submit Sales Invoice to EFRIS."),
									);
								}
							} catch (error) {
								console.error("Error submitting to EFRIS:", error);

								frappe.msgprint(
									__("An error occurred while submitting to EFRIS."),
								);
							}
						},
						function () {
							console.log("Submission to EFRIS was cancelled by the user.");
						},
					);
				});
			}
		}, 1000);

		if (frm.doc.docstatus === 0 && frm.doc.efris_company && frm.doc.efris_invoice) {
			frm.add_custom_button(__("Recover EFRIS Invoice"), function () {
				let d = new frappe.ui.Dialog({
					title: __("Recover EFRIS Invoice"),
					fields: [
						{
							label: __("FDN Number"),
							fieldname: "fdn",
							fieldtype: "Data",
							reqd: 1,
							description: __("Enter the FDN Number received from EFRIS."),
						},
					],
					primary_action_label: __("Recover"),
					primary_action(values) {
						console.log("FDN entered:", values.fdn);

						d.hide();

						frappe.call({
							method: "yana_efris.api.efris_api.recover_efris_invoice",
							args: {
								sales_invoice_name: frm.doc.name,
								fdn: values.fdn,
							},
							freeze: true,
							freeze_message: __("Fetching invoice from EFRIS..."),
							callback: function (r) {
								console.log("EFRIS Recovery Response", r.message);

								if (r.message.success) {
									frappe.msgprint({
										title: __("Success"),
										message: __("Invoice recovered successfully."),
										indicator: "green",
									});

									// Redirect to renamed SAL invoice
									if (r.message.invoice_name) {
										frappe.set_route(
											"Form",
											"Sales Invoice",
											r.message.invoice_name,
										);
									}
								} else {
									frappe.msgprint({
										title: __("Error"),
										message: r.message.error || __("Invalid FDN Number."),
										indicator: "red",
									});
								}
							},
						});

						// Backend call will come in Step 2
					},
				});

				d.show();
			});
		}
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

				frm.set_value("custom_customer_outstanding_amount", data.outstanding);

				// frappe.msgprint({
				// 	title: "Customer Credit Information",
				// 	indicator: data.overdue_count > 0 ? "red" : "green",
				// 	message: `
				//         <b>Outstanding Amount:</b> ${format_currency(data.outstanding)} <br>
				//         <b>Overdue Invoices:</b> ${data.overdue_count} <br>
				//         <b>Oldest Overdue:</b> ${data.oldest_days} days
				//     `,
				// });
			},
		});
	},
	company(frm) {
		if (frm.doc.company) {
			// frappe.call({
			// 	method: "yana_efris.api.efris_api.fetch_efris_branches",
			// 	args: {
			// 		company_name: frm.doc.company,
			// 	},
			// 	// callback: (r) => console.log("frappe.call ok", r),
			// 	error: (err) => console.error("frappe.call err", err),
			// });
			// Step 1: Fetch company flag
			frappe.db.get_value("Company", frm.doc.company, "efris_company").then((r) => {
				const is_efris = r.message?.efris_company;

				// Step 2: Only call API if EFRIS company
				if (is_efris) {
					// frappe.call({
					// 	method: "yana_efris.api.efris_api.fetch_efris_branches",
					// 	args: {
					// 		company_name: frm.doc.company,
					// 	},
					// 	error: (err) => console.error("EFRIS API error", err),
					// });
				} else {
					console.log("Non-EFRIS company selected, skipping API");

					// Optional: clear EFRIS-related fields if any
					// frm.set_value("branch", null);
				}
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
			console.log("Customer lookup result:", r);
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
										frappe.msgprint(r.message.message);
									}
								},
								error: function (err) {
									console.error("❌ API Error:", err);
									frappe.msgprint(
										"Failed to fetch customer details from EFRIS.",
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

// frappe.ui.form.on("Sales Invoice Item", {
// 	item_code: function (frm, cdt, cdn) {
// 		const row = frappe.get_doc(cdt, cdn);
// 		if (!row.item_code) return;

// 		frappe.call({
// 			method: "yana_efris.api.efris_api.fetch_live_stock_by_goods_code",
// 			args: {
// 				goods_code: row.item_code,
// 				company: frm.doc.company,
// 			},
// 			callback: function (r) {
// 				if (!r.message) return;
// 				console.log("Stock Quantity", r);

// 				if (r.message.success) {
// 					const stock = r.message.live_stock;
// 					const item_id = r.message.efris_item_id;

// 					frappe.model.set_value(cdt, cdn, "custom_efris_live_stock", stock);

// 					frappe.show_alert({
// 						message: `Live EFRIS stock for ${row.item_code}: <b>${stock}</b>`,
// 						indicator: "green",
// 					});

// 					console.log(`EFRIS ID stored: ${item_id}`);
// 				} else {
// 					frappe.show_alert({
// 						message: `EFRIS stock fetch failed: ${r.message.message || "Error"}`,
// 						indicator: "red",
// 					});
// 				}
// 			},
// 		});
// 	},
// });

frappe.ui.form.on("Sales Invoice Item", {
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
					console.log("Actual Item Code", actual_item_code);

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
