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

				switch_company(first_company);

				return;
			}

			render_company_dropdown(companies);
		},
	});
}

function should_show_company_switcher() {
	let route = frappe.get_route();

	console.log("Route is", route);

	return route && route[0] === "Workspaces" && route[1] === "Home";
}

function toggle_company_switcher_visibility() {
	if (should_show_company_switcher()) {
		$("#company-switcher-wrapper").show();
	} else {
		$("#company-switcher-wrapper").hide();
	}
}

function render_company_dropdown(companies) {
	// Prevent duplicate rendering
	if ($("#company-switcher-wrapper").length) {
		toggle_company_switcher_visibility();
		return;
	}

	let current_company = frappe.defaults.get_user_default("company");

	let options = companies
		.map((c) => {
			let selected = c === current_company ? "selected" : "";

			return `<option value="${c}" ${selected}>${c}</option>`;
		})
		.join("");

	let dropdown = $(`
		<div id="company-switcher-wrapper">
			<select id="company-switcher"
				style="
					margin-left: 12px;
					padding: 5px;
					border-radius: 6px;
				">
				${options}
			</select>
		</div>
	`);

	let interval = setInterval(() => {
		if ($(".navbar .search-bar").length) {
			$(".navbar .search-bar").after(dropdown);

			clearInterval(interval);

			toggle_company_switcher_visibility();
		}
	}, 200);
}

frappe.router.on("change", function () {
	console.log("Route changed");

	setTimeout(() => {
		toggle_company_switcher_visibility();
	}, 200);
});

$(document).on("change", "#company-switcher", function () {
	let company = $(this).val();
	switch_company(company);
});

function switch_company(company) {
	frappe.call({
		method: "yana_efris.api.efris_api.set_active_company",
		args: {
			company: company,
		},
		callback: function () {
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
