// console.log("Permission Override JS Loaded");

// frappe.after_ajax(function () {
// 	if (window.__permission_override_applied) return;
// 	window.__permission_override_applied = true;

// 	const original_msgprint = frappe.msgprint;

// 	frappe.msgprint = function (msg, title, is_minimizable) {
// 		try {
// 			let message_text = "";
// 			console.log("Message text is", msg);

// 			if (typeof msg === "string") {
// 				message_text = msg;
// 			} else if (typeof msg === "object" && !Array.isArray(msg)) {
// 				message_text = msg.message || "";
// 			} else if (Array.isArray(msg) && msg.length > 0) {
// 				message_text = msg[0].message || "";
// 			}

// 			if (
// 				message_text.includes("Document renamed from") &&
// 				message_text.includes("to <strong>")
// 			) {
// 				const match = message_text.match(/to <strong>(.*?)<\/strong>/);

// 				if (match && match[1]) {
// 					const newInvoiceName = match[1];

// 					// Already on SAL? Do nothing.
// 					if (cur_frm?.doc?.name !== newInvoiceName) {
// 						console.log("Redirecting to renamed invoice:", newInvoiceName);

// 						setTimeout(() => {
// 							frappe.set_route("Form", "Sales Invoice", newInvoiceName);

// 							setTimeout(() => {
// 								console.log("Location Reload success");
// 								window.location.reload();
// 							}, 1000);
// 						}, 1500);
// 					}
// 				}
// 			}

// 			if (
// 				message_text.includes("does not have doctype access") ||
// 				message_text.includes("No permission for") ||
// 				message_text.includes("Not permitted") ||
// 				message_text.includes("The resource you are looking for is not available")
// 			) {
// 				// 🔥 Prevent duplicate popup within 1 second
// 				if (window.__subscription_popup_active) {
// 					return;
// 				}

// 				window.__subscription_popup_active = true;

// 				setTimeout(function () {
// 					window.__subscription_popup_active = false;
// 				}, 1000); // cooldown 1 second

// 				console.group("🔴 Original Permission Message");
// 				console.log(message_text);
// 				console.groupEnd();

// 				return original_msgprint({
// 					title: "Access Denied - Contact Admin",
// 					message: "Access Denied - Contact Admin to get the access of this module",
// 					indicator: "orange",
// 				});
// 			}
// 			if (
// 				message_text.includes("You don't have access to Report") ||
// 				message_text.includes("You don't have permission to get a report on")
// 			) {
// 				// 🔥 Prevent duplicate popup within 1 second
// 				if (window.__subscription_popup_active) {
// 					return;
// 				}

// 				window.__subscription_popup_active = true;

// 				setTimeout(function () {
// 					window.__subscription_popup_active = false;
// 				}, 1000); // cooldown 1 second

// 				console.group("🔴 Original Permission Message");
// 				console.log(message_text);
// 				console.groupEnd();

// 				return original_msgprint({
// 					title: "Access Denied - Contact Admin",
// 					message: "Access Denied - Contact Admin to get the access of this report",
// 					indicator: "orange",
// 				});
// 			}
// 		} catch (e) {
// 			console.warn("Permission override error:", e);
// 		}

// 		return original_msgprint(msg, title, is_minimizable);
// 	};
// });

// Above code is for backup. New code is below:

console.log("Permission Override JS Loaded");

(function () {
	if (window.__permission_override_applied) return;

	if (!frappe || typeof frappe.msgprint !== "function") {
		console.warn("frappe.msgprint is not available yet");
		return;
	}

	window.__permission_override_applied = true;

	const original_msgprint = frappe.msgprint;

	function extractMessage(value) {
		if (!value) return "";

		if (typeof value === "string") {
			return value;
		}

		if (Array.isArray(value)) {
			return value.map(extractMessage).join(" ");
		}

		if (typeof value === "object") {
			return [value.message, value.title].map(extractMessage).join(" ");
		}

		return String(value);
	}

	frappe.msgprint = function (msg, title, is_minimizable) {
		try {
			const message_text = extractMessage(msg);
			const title_text = extractMessage(title);

			const full_text = (message_text + " " + title_text).toLowerCase();

			console.log("Permission Override Message:", full_text);

			// --------------------------------
			// 1. Sales Invoice Rename Redirect
			// --------------------------------

			if (
				message_text.includes("Document renamed from") &&
				message_text.includes("to <strong>")
			) {
				const match = message_text.match(/to <strong>(.*?)<\/strong>/);

				if (match && match[1]) {
					const newInvoiceName = match[1];

					if (cur_frm?.doc?.name !== newInvoiceName) {
						console.log("Redirecting to renamed invoice:", newInvoiceName);

						setTimeout(() => {
							frappe.set_route("Form", "Sales Invoice", newInvoiceName);

							setTimeout(() => {
								window.location.reload();
							}, 1000);
						}, 1500);
					}
				}
			}

			// --------------------------------
			// 2. Report Permission Errors
			// --------------------------------

			const is_report_error =
				full_text.includes("you don't have access to report") ||
				full_text.includes("you don't have permission to get a report on");

			// --------------------------------
			// 3. General Permission Errors
			// --------------------------------

			const permission_patterns = [
				"does not have doctype access",
				"no permission for",
				"not permitted",
				"the resource you are looking for is not available",
				"you are not allowed to access",
				"does not have access to this document",
				"insufficient permission for",
			];

			const is_permission_error = permission_patterns.some((pattern) =>
				full_text.includes(pattern),
			);

			// --------------------------------
			// 4. Replace Permission Popup
			// --------------------------------

			if (is_report_error || is_permission_error) {
				if (window.__permission_popup_active) {
					return;
				}

				window.__permission_popup_active = true;

				setTimeout(() => {
					window.__permission_popup_active = false;
				}, 1200);

				console.group("Permission Error Intercepted");
				console.log("Original Title:", title_text);
				console.log("Original Message:", message_text);
				console.groupEnd();

				return original_msgprint({
					title: "Access Denied - Contact Admin",
					message: is_report_error
						? "Access Denied - Contact Admin to get the access of this report"
						: "Access Denied - Contact Admin to get the access of this module",
					indicator: "orange",
				});
			}
		} catch (e) {
			console.warn("Permission override error:", e);
		}

		return original_msgprint(msg, title, is_minimizable);
	};

	console.log("Permission Override Successfully Applied");
})();
