frappe.provide("yana_efris");

frappe.listview_settings = frappe.listview_settings || {};

(function () {
	if (
		!frappe.views ||
		!frappe.views.ListView ||
		frappe.views.ListView.prototype._yana_cancellation_patched
	) {
		return;
	}

	const original_get_actions_menu_items = frappe.views.ListView.prototype.get_actions_menu_items;

	frappe.views.ListView.prototype.get_actions_menu_items = function () {
		const items = original_get_actions_menu_items.apply(this, arguments);

		const cancel_item = items.find((item) => {
			return item && item.label === __("Cancel");
		});

		if (!cancel_item) {
			return items;
		}

		const original_action = cancel_item.action;
		const listview = this;

		cancel_item.action = function () {
			const checked_items = listview.get_checked_items(true);

			if (!checked_items || !checked_items.length) {
				frappe.msgprint(__("Please select at least one document."));
				return;
			}

			frappe.confirm(__("Cancel {0} documents?", [checked_items.length]), function () {
				show_cancellation_reason_dialog(listview, checked_items, original_action);
			});
		};

		return items;
	};

	frappe.views.ListView.prototype._yana_cancellation_patched = true;

	function show_cancellation_reason_dialog(listview, checked_items, original_action) {
		const dialog = new frappe.ui.Dialog({
			title: __("Cancellation Reason"),
			fields: [
				{
					fieldname: "cancellation_reason",
					fieldtype: "Small Text",
					label: __("Cancellation Reason"),
					reqd: 1,
				},
			],
			primary_action_label: __("Submit"),
			primary_action(values) {
				const reason = (values.cancellation_reason || "").trim();

				if (!reason) {
					frappe.msgprint({
						title: __("Cancellation Reason Required"),
						message: __("Cancellation reason is mandatory."),
						indicator: "red",
					});
					return;
				}

				dialog.disable_primary_action();

				cancel_documents(listview, checked_items, reason, dialog);
			},
		});

		dialog.show();
	}

	function cancel_documents(listview, checked_items, cancellation_reason, dialog) {
		const doctype = listview.doctype;

		const documents = checked_items.map((row) => {
			return row.name || row;
		});

		let completed = 0;
		let failed = false;

		const cancel_next = function () {
			if (failed) {
				return;
			}

			if (completed >= documents.length) {
				dialog.hide();

				frappe.show_alert({
					message: __("{0} document(s) cancelled.", [documents.length]),
					indicator: "red",
				});

				listview.clear_checked_items();
				listview.refresh();

				return;
			}

			const name = documents[completed];

			frappe
				.call({
					method: "yana_efris.api.efris_api.cancel_document",
					type: "POST",
					args: {
						doctype: doctype,
						name: name,
						cancellation_reason: cancellation_reason,
					},
					freeze: true,
					freeze_message: __("Cancelling {0} of {1} documents...", [
						completed + 1,
						documents.length,
					]),
				})
				.then(() => {
					completed++;
					cancel_next();
				})
				.catch((error) => {
					failed = true;

					dialog.enable_primary_action();

					frappe.msgprint({
						title: __("Cancellation Failed"),
						message: error?.message || __("Unable to cancel {0}.", [name]),
						indicator: "red",
					});
				});
		};

		cancel_next();
	}
})();
