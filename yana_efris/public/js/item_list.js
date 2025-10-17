frappe.listview_settings["Item"] = {
	onload(listview) {
		listview.page.add_button(__("Fetch Items from EFRIS"), () => {
			console.log("Fetch EFRIS Items Button Clicked");
			// call our server method (to be created)
			frappe.call({
				method: "yana_efris.api.efris_item_sync.enqueue_sync_efris_items",
				args: {
					company_name: "MERCIA HOSPITALITY SOLUTIONS LIMITED",
					page_size: 25,
					chunk_size: 1,
				},
				freeze: true,
				freeze_message: __("Fetching items from EFRIS..."),
				callback: function (r) {
					if (r.message) {
						console.log("Response successfull", r);
					}
				},
			});
		});
	},
};
