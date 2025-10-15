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
frappe.ui.form.on("Sales Invoice", {
	refresh: async function (frm) {
		console.log("This console is working");

		// Only for Return (Credit Note) invoices
		if (frm.doc.is_return && frm.doc.efris_e_invoice) {
			try {
				// Fetch linked E-Invoice document
				const e_invoice = await frappe.db.get_doc("E Invoice", frm.doc.efris_e_invoice);

				console.log(
					"[YANA EFRIS] Hiding 'Submit To EFRIS' button as invoice already submitted."
				);
				// Wait until buttons render, then hide them
				setTimeout(() => {
					$('.btn:contains("Submit To EFRIS")').hide();
				}, 300);

				// Now check the E-Invoice status from that document
				if (e_invoice.status === "EFRIS Credit Note Pending") {
					console.log(
						"[YANA EFRIS] Showing 'Check EFRIS Approval Status' button for Credit Note."
					);

					frm.add_custom_button(__("Check EFRIS Approval Status"), async function () {
						if (frm.is_dirty()) {
							frappe.throw({
								message: __(
									"You must save the document before making e-invoicing request."
								),
								title: __("Unsaved Document"),
							});
							return;
						}

						await frm.reload_doc();

						try {
							await frappe.call({
								method: "uganda_compliance.efris.api_classes.e_invoice.confirm_irn_cancellation",
								args: { sales_invoice: frm.doc },
								freeze: true,
								freeze_message: __("Checking approval status from EFRIS..."),
							});
							await frm.reload_doc();
						} catch (error) {
							console.error(
								`[YANA EFRIS] Error confirming IRN cancellation:`,
								error
							);
							frappe.msgprint(
								__("Error while checking approval status from EFRIS.")
							);
						}
					});
				} else {
					console.log(
						`[YANA EFRIS] No action button shown, status = ${e_invoice.einvoice_status}`
					);
				}
			} catch (error) {
				console.error("[YANA EFRIS] Failed to fetch linked E-Invoice:", error);
			}
		}
	},
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
				return; // ❌ This only stops THEN, so we need return outside
			} else {
				// ✅ Safe to call API here (only when customer doesn’t exist)
				const e_company_name = frm.doc.company;
				const ninBrn = "";

				frappe.call({
					method: "yana_efris.api.efris_api.query_customer_details",
					args: {
						doc: frm.doc.name, // ✅ doc_name instead of doc
						e_company_name,
						tax_id: tin,
						ninBrn,
					},
					freeze: true,
					freeze_message: __("Fetching customer details from EFRIS..."),
					callback: function (r) {
						if (r.message) {
							frm.set_value("customer", r.message.taxpayer.legalName);
							frappe.msgprint("Customer details fetched successfully!");
						}
					},
					error: function (err) {
						console.error("❌ API Error:", err);
						frappe.msgprint("Failed to fetch customer details from EFRIS.");
					},
				});
			}
		});
	},

	custom_is_new_customer: function (frm) {
		frm.set_value("custom_new_customer_tin", "");
	},
});
