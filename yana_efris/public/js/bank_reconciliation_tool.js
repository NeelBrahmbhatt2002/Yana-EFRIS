frappe.ui.form.on("Bank Reconciliation Tool", {
	setup: function (frm) {
		console.log("Custom code called");
		frm.set_query("company", function () {
			return {
				query: "yana_efris.api.efris_api.get_user_companies",
			};
		});
	},
});
