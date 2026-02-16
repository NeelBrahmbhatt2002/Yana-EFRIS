console.log("Permission Override JS Loaded");

frappe.after_ajax(function () {
	if (window.__permission_override_applied) return;
	window.__permission_override_applied = true;

	const original_msgprint = frappe.msgprint;

	frappe.msgprint = function (msg, title, is_minimizable) {
		try {
			let message_text = "";
			console.log("Message text is", msg);

			if (typeof msg === "string") {
				message_text = msg;
			} else if (typeof msg === "object" && !Array.isArray(msg)) {
				message_text = msg.message || "";
			} else if (Array.isArray(msg) && msg.length > 0) {
				message_text = msg[0].message || "";
			}

			if (
				message_text.includes("does not have doctype access") ||
				message_text.includes("No permission for") ||
				message_text.includes("Not permitted") ||
				message_text.includes("Page not found") ||
				message_text.includes("The resource you are looking for is not available")
			) {
				// 🔥 Prevent duplicate popup within 1 second
				if (window.__subscription_popup_active) {
					return;
				}

				window.__subscription_popup_active = true;

				setTimeout(function () {
					window.__subscription_popup_active = false;
				}, 1000); // cooldown 1 second

				console.group("🔴 Original Permission Message");
				console.log(message_text);
				console.groupEnd();

				return original_msgprint({
					title: "Subscription Required",
					message: "Please take subscription to get the access of this module",
					indicator: "orange",
				});
			}
			if (
				message_text.includes("You don't have access to Report") ||
				message_text.includes("You don't have permission to get a report on")
			) {
				// 🔥 Prevent duplicate popup within 1 second
				if (window.__subscription_popup_active) {
					return;
				}

				window.__subscription_popup_active = true;

				setTimeout(function () {
					window.__subscription_popup_active = false;
				}, 1000); // cooldown 1 second

				console.group("🔴 Original Permission Message");
				console.log(message_text);
				console.groupEnd();

				return original_msgprint({
					title: "Subscription Required",
					message: "Please take subscription to get the access of this report",
					indicator: "orange",
				});
			}
		} catch (e) {
			console.warn("Permission override error:", e);
		}

		return original_msgprint(msg, title, is_minimizable);
	};
});
