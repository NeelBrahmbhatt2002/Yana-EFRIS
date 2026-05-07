frappe.after_ajax(() => {
	setTimeout(() => {
		get_user_companies();
	}, 500);
});

function get_user_companies() {
	frappe.call({
		method: "frappe.client.get_list",
		args: {
			doctype: "User Permission",
			filters: {
				user: frappe.session.user,
				allow: "Company",
			},
			fields: ["for_value"],
		},
		callback: function (res) {
			if (!res.message || res.message.length <= 1) return;

			let companies = res.message.map((c) => c.for_value);

			// CHECK CURRENT DEFAULT COMPANY
			let current_company = frappe.defaults.get_user_default("company");

			// IF NO COMPANY ASSIGNED
			if (!current_company) {
				let first_company = companies[0];

				console.log("No default company found");
				console.log("Assigning:", first_company);

				switch_company(first_company);

				return;
			}

			render_company_dropdown(companies);
		},
	});
}

function render_company_dropdown(companies) {
	let current_company = frappe.defaults.get_user_default("company");

	let options = companies
		.map((c) => {
			let selected = c === current_company ? "selected" : "";
			return `<option value="${c}" ${selected}>${c}</option>`;
		})
		.join("");

	let dropdown = $(`
		<select id="company-switcher"
			style="margin-left: 12px; padding: 5px; border-radius: 6px;">
			${options}
		</select>
	`);

	// Wait until navbar exists
	let interval = setInterval(() => {
		if ($(".navbar .search-bar").length) {
			$(".navbar .search-bar").after(dropdown);
			clearInterval(interval);
		}
	}, 200);

	$(document).on("change", "#company-switcher", function () {
		console.log("Dropdown changed ✅");
		let company = $(this).val();
		console.log("Selected company:", company);
		console.log("Current default BEFORE API:", frappe.defaults.get_user_default("company"));
		switch_company(company);
	});
}

function switch_company(company) {
	frappe.call({
		method: "yana_efris.api.efris_api.set_active_company",
		args: {
			company: company,
		},
		callback: function () {
			console.log("AFTER API call:");
			console.log("Selected company:", company);
			console.log("Current default AFTER API:", frappe.defaults.get_user_default("company"));
			frappe.show_alert({
				message: `Switched to ${company}`,
				indicator: "green",
			});

			// Reload dashboard to refresh data
			setTimeout(() => {
				location.reload();
			}, 500);
		},
	});
}
