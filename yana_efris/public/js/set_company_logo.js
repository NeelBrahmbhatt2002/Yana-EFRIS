(function () {
	$(document).ready(function () {
		console.log("Company logo script loaded");

		setTimeout(() => {
			load_company_logo();
		}, 500);
	});

	function load_company_logo() {
		frappe.call({
			method: "yana_efris.api.efris_api.get_user_company_logo",
			callback: function (res) {
				let logo = res.message;

				console.log("Logo:", logo);

				// ❌ No logo → keep default
				if (!logo) return;

				let header_logo = document.querySelector(".navbar .app-logo");

				if (header_logo) {
					header_logo.src = logo;
					console.log("✅ Logo updated");
				}
			},
		});
	}
})();
