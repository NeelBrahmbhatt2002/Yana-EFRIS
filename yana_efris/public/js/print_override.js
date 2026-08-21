(function () {
	// ✅ Global click handler (always works)
	// $(document).on("click", "#custom-pdf-btn", function () {
	// 	console.log("Custom PDF clicked");

	// 	let path_parts = window.location.pathname.split("/");
	// 	let doctype = path_parts[3];
	// 	let name = path_parts[4];

	// 	let format =
	// 		document.querySelector('[data-fieldname="print_format"] input')?.value || "Standard";

	// 	let url = `/api/method/yana_efris.api.efris_api.download_invoice_pdf?doctype=${doctype}&name=${name}&format=${encodeURIComponent(format)}`;

	// 	let a = document.createElement("a");
	// 	a.href = url;
	// 	a.download = `${name}.pdf`;
	// 	document.body.appendChild(a);
	// 	a.click();
	// 	document.body.removeChild(a);
	// });

	$(document).on("click", "#custom-pdf-btn", async function () {
		console.log("Custom PDF clicked");

		let path_parts = window.location.pathname.split("/");
		let doctype = decodeURIComponent(path_parts[3]);
		let name = decodeURIComponent(path_parts[4]);

		let format =
			document.querySelector('[data-fieldname="print_format"] input')?.value || "Standard";

		console.log("Custom PDF details:", {
			doctype: doctype,
			name: name,
			format: format,
		});

		try {
			const response = await fetch(
				"/api/method/yana_efris.api.efris_api.download_invoice_pdf",
				{
					method: "POST",
					headers: {
						"Content-Type": "application/x-www-form-urlencoded",
						"X-Frappe-CSRF-Token": frappe.csrf_token,
					},
					body: new URLSearchParams({
						doctype: doctype,
						name: name,
						format: format,
					}),
				},
			);

			console.log("PDF response status:", response.status);

			if (!response.ok) {
				const error_data = await response.json().catch(() => null);

				console.error("PDF generation failed:", error_data);

				let message = "Unable to generate PDF.";

				if (error_data?._server_messages) {
					try {
						const server_messages = JSON.parse(error_data._server_messages);

						if (server_messages.length) {
							message = JSON.parse(server_messages[0]).message;
						}
					} catch (e) {
						console.error("Could not parse server message:", e);
					}
				}

				frappe.msgprint({
					title: "Printing Not Allowed",
					message: message,
					indicator: "red",
				});

				return;
			}

			const blob = await response.blob();

			const blob_url = window.URL.createObjectURL(blob);

			const a = document.createElement("a");
			a.href = blob_url;
			a.download = `${name}.pdf`;

			document.body.appendChild(a);
			a.click();
			document.body.removeChild(a);

			window.URL.revokeObjectURL(blob_url);

			console.log("PDF downloaded successfully");
		} catch (error) {
			console.error("PDF download error:", error);

			frappe.msgprint({
				title: "PDF Error",
				message: "An error occurred while generating the PDF.",
				indicator: "red",
			});
		}
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

		// Remove default Print button
		$(".page-actions button").each(function () {
			const text = $(this).text().trim();

			if (text === "Print") {
				console.log("Removing default Print button");
				$(this).remove();
			}
		});

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
