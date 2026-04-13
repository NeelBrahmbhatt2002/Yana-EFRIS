(function () {
	// ✅ Global click handler (always works)
	$(document).on("click", "#custom-pdf-btn", function () {
		console.log("Custom PDF clicked");

		let path_parts = window.location.pathname.split("/");
		let doctype = path_parts[3];
		let name = path_parts[4];

		let format =
			document.querySelector('[data-fieldname="print_format"] input')?.value || "Standard";

		let url = `/api/method/yana_efris.api.efris_api.download_invoice_pdf?doctype=${doctype}&name=${name}&format=${encodeURIComponent(format)}`;

		let a = document.createElement("a");
		a.href = url;
		a.download = `${name}.pdf`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
	});

	// 🔥 Observe DOM changes (THIS IS THE KEY)
	const observer = new MutationObserver(() => {
		apply_print_override();
	});

	observer.observe(document.body, {
		childList: true,
		subtree: true,
	});

	function apply_print_override() {
		let is_print_page = window.location.pathname.includes("/print/");

		// ❌ Remove button everywhere except print page
		if (!is_print_page) {
			if ($("#custom-pdf-btn").length) {
				console.log("Removing custom button (not print page)");
				$("#custom-pdf-btn").remove();
			}
			return;
		}

		// ✅ Ensure page-actions exists
		let actions = document.querySelector(".page-actions");
		if (!actions) return;

		// Remove default PDF button
		$(".page-actions button").each(function () {
			if ($(this).text().trim() === "PDF" && this.id !== "custom-pdf-btn") {
				$(this).remove();
			}
		});

		// Prevent duplicate
		if ($("#custom-pdf-btn").length) return;

		console.log("Adding custom PDF button");

		// Add custom button
		let btn = $(`
			<button id="custom-pdf-btn" class="btn btn-primary btn-sm">
				PDF
			</button>
		`);

		$(".page-actions").append(btn);
	}
})();
