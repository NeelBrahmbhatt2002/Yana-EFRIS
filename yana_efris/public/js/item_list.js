frappe.listview_settings["Item"] = {
	onload(listview) {
		if (frappe.user.has_role("System Manager")) {
			frappe.db
				.get_value(
					"User Permission",
					{ user: frappe.session.user, allow: "Company" },
					"for_value"
				)
				.then((res) => {
					const company_name = res?.message?.for_value;

					if (!company_name) {
						frappe.msgprint({
							title: __("No Company Assigned"),
							message: __(
								"You do not have a company assigned in your User Permissions."
							),
							indicator: "red",
						});
						return;
					}

					listview.page.add_button(__("Fetch Items from EFRIS"), () => {
						frappe.call({
							method: "yana_efris.api.efris_item_sync.enqueue_sync_efris_items",
							args: {
								company_name: company_name,
								page_size: 25,
								chunk_size: 1,
							},
							freeze: true,
							freeze_message: __("Fetching items from EFRIS..."),
							callback: function (r) {
								if (r.message) {
									frappe.msgprint({
										title: __("EFRIS Sync Started"),
										indicator: "green",
										message: __(
											`EFRIS sync started for <b>${company_name}</b>. Please refresh after a few minutes.`
										),
									});
								}
							},
						});
					});
				});
		}
	},
};
