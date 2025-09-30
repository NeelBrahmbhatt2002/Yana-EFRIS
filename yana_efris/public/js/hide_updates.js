frappe.ready(() => {
	frappe.xcall = (function (orig_xcall) {
		return function (method, ...args) {
			// Block update popup call
			console.log("Function is running");
			if (method === "frappe.utils.change_log.show_update_popup") {
				console.log("🔒 Update popup suppressed");
				return Promise.resolve(); // do nothing
			}
			return orig_xcall.apply(this, [method, ...args]);
		};
	})(frappe.xcall);
});
