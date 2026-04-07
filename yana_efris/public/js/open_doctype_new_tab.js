$(document).on("mousedown", "a[href^='/app/']", function (e) {
	// Allow Ctrl / Cmd / middle-click
	if (e.ctrlKey || e.metaKey || e.which === 2) return;

	const href = this.getAttribute("href");
	if (!href) return;

	// Ignore workspace root itself
	if (href.startsWith("/app/query-report/") || href.startsWith("/app/report/")) {
		frappe.open_in_new_tab = true;
	}

	// 🔑 THIS is the key line
	// frappe.open_in_new_tab = true;
});

// ✅ NEW: Handle POSNext shortcut widget
// POSNext shortcut fix (no double tab)
$(document).on("mousedown", ".shortcut-widget-box", function (e) {
	const label = this.getAttribute("aria-label") || "";

	if (label === "Start POS") {
		// 🔥 Stop EVERYTHING
		e.preventDefault();
		e.stopImmediatePropagation();

		// Open only once
		window.open("/pos", "_blank");

		return false;
	}
});
