frappe.provide("yana_efris.cancellation");

yana_efris.cancellation.setup_form_cancel_override = function () {
	if (!frappe.ui.form.Form || !frappe.ui.form.Form.prototype._cancel) {
		return;
	}

	if (frappe.ui.form.Form.prototype._yana_efris_cancel_overridden) {
		return;
	}

	const original_cancel = frappe.ui.form.Form.prototype._cancel;

	frappe.ui.form.Form.prototype._cancel = function (btn, callback, on_error, skip_confirm) {
		const me = this;

		// Preserve the standard behaviour when cancellation
		// is explicitly requested without confirmation.
		if (skip_confirm) {
			return original_cancel.call(me, btn, callback, on_error, true);
		}

		// --------------------------------------------------
		// STEP 1: Standard confirmation popup
		// --------------------------------------------------
		frappe.confirm(
			__("Permanently Cancel {0}?", [me.doc.name]),
			function () {
				// User clicked Yes
				show_cancellation_reason_dialog();
			},
			function () {
				// User clicked No
				return;
			},
		);

		// --------------------------------------------------
		// STEP 2: Cancellation reason popup
		// --------------------------------------------------
		function show_cancellation_reason_dialog() {
			const d = new frappe.ui.Dialog({
				title: __("Cancellation Reason"),
				fields: [
					{
						fieldtype: "Long Text",
						fieldname: "cancellation_reason",
						label: __("Cancellation Reason"),
						reqd: 1,
						description: __("Please provide a reason for cancelling this document."),
					},
				],
				primary_action_label: __("Submit"),

				primary_action: function () {
					const values = d.get_values();

					if (!values || !values.cancellation_reason) {
						frappe.msgprint({
							message: __("Cancellation reason is mandatory."),
							indicator: "red",
							title: __("Cancellation Reason Required"),
						});
						return;
					}

					const cancellation_reason = values.cancellation_reason.trim();

					if (!cancellation_reason) {
						frappe.msgprint({
							message: __("Cancellation reason is mandatory."),
							indicator: "red",
							title: __("Cancellation Reason Required"),
						});
						return;
					}

					d.hide();

					frappe.validated = true;

					me.script_manager.trigger("before_cancel").then(() => {
						if (!frappe.validated) {
							me.handle_save_fail(btn, on_error);
							return;
						}

						const after_cancel = function (r) {
							if (r.exc) {
								me.handle_save_fail(btn, on_error);
								return;
							}

							frappe.utils.play_sound("cancel");

							if (r.docs) {
								frappe.model.sync(r.docs);
							}

							me.refresh();

							callback && callback();

							me.script_manager.trigger("after_cancel");
						};

						const args = {
							doctype: me.doc.doctype,
							name: me.doc.name,
							cancellation_reason: cancellation_reason,
						};

						// Preserve workflow cancellation behaviour.
						const workflow_state_fieldname = frappe.workflow.get_state_fieldname(
							me.doctype,
						);

						if (workflow_state_fieldname) {
							args.workflow_state_fieldname = workflow_state_fieldname;
							args.workflow_state = me.doc[workflow_state_fieldname];
						}

						frappe.call({
							method: "frappe.desk.form.save.cancel",
							args: args,
							freeze: true,
							btn: btn,
							callback: after_cancel,
							error: function () {
								me.handle_save_fail(btn, on_error);
							},
						});
					});
				},
			});

			d.show();

			// Focus the cancellation reason field.
			d.fields_dict.cancellation_reason.$input.focus();
		}
	};

	frappe.ui.form.Form.prototype._yana_efris_cancel_overridden = true;
};

yana_efris.cancellation.setup_cancel_all_override = function () {
	if (!frappe.ui.form.Form || !frappe.ui.form.Form.prototype._cancel_all) {
		return;
	}

	if (frappe.ui.form.Form.prototype._yana_efris_cancel_all_overridden) {
		return;
	}

	const original_cancel_all = frappe.ui.form.Form.prototype._cancel_all;

	frappe.ui.form.Form.prototype._cancel_all = function (r, btn, callback, on_error) {
		const me = this;

		// --------------------------------------------------
		// Build the standard "Cancel All Documents" message
		// --------------------------------------------------
		let links_text = "";
		let links = r.message.docs;
		const doctypes = Array.from(new Set(links.map((link) => link.doctype)));

		me.ignore_doctypes_on_cancel_all = me.ignore_doctypes_on_cancel_all || [];

		for (let doctype of doctypes) {
			if (!me.ignore_doctypes_on_cancel_all.includes(doctype)) {
				let docnames = links
					.filter((link) => link.doctype == doctype)
					.map((link) => frappe.utils.get_form_link(link.doctype, link.name, true))
					.join(", ");

				links_text += `<li><strong>${__(doctype)}</strong>: ${docnames}</li>`;
			}
		}

		links_text = `<ul>${links_text}</ul>`;

		let confirm_message = __("{0} {1} is linked with the following submitted documents: {2}", [
			__(me.doc.doctype).bold(),
			me.doc.name,
			links_text,
		]);

		let can_cancel = links.every((link) => frappe.model.can_cancel(link.doctype));

		if (can_cancel) {
			confirm_message += __("Do you want to cancel all linked documents?");
		} else {
			confirm_message += __("You do not have permissions to cancel all linked documents.");
		}

		// --------------------------------------------------
		// Standard Cancel All Documents dialog
		// --------------------------------------------------
		let d = new frappe.ui.Dialog(
			{
				title: __("Cancel All Documents"),
				fields: [
					{
						fieldtype: "HTML",
						options: `<p class="frappe-confirm-message">${confirm_message}</p>`,
					},
				],
			},
			() => me.handle_save_fail(btn, on_error),
		);

		// --------------------------------------------------
		// Cancel All button
		// --------------------------------------------------
		if (can_cancel) {
			d.set_primary_action(__("Cancel All"), () => {
				d.hide();

				// ------------------------------------------
				// Ask for cancellation reason
				// ------------------------------------------
				const reason_dialog = new frappe.ui.Dialog({
					title: __("Cancellation Reason"),
					fields: [
						{
							fieldtype: "Long Text",
							fieldname: "cancellation_reason",
							label: __("Cancellation Reason"),
							reqd: 1,
							description: __(
								"Please provide a reason for cancelling this document.",
							),
						},
					],
					primary_action_label: __("Submit"),

					primary_action: function () {
						const values = reason_dialog.get_values();

						if (!values || !values.cancellation_reason) {
							frappe.msgprint({
								message: __("Cancellation reason is mandatory."),
								indicator: "red",
								title: __("Cancellation Reason Required"),
							});
							return;
						}

						const cancellation_reason = values.cancellation_reason.trim();

						if (!cancellation_reason) {
							frappe.msgprint({
								message: __("Cancellation reason is mandatory."),
								indicator: "red",
								title: __("Cancellation Reason Required"),
							});
							return;
						}

						reason_dialog.hide();

						// --------------------------------------
						// Cancel linked documents
						// --------------------------------------
						frappe.call({
							method: "frappe.desk.form.linked_with.cancel_all_linked_docs",

							args: {
								docs: links,
								ignore_doctypes_on_cancel_all:
									me.ignore_doctypes_on_cancel_all || [],
							},

							freeze: true,

							callback: (resp) => {
								if (resp.exc) {
									me.handle_save_fail(btn, on_error);
									return;
								}

								// ----------------------------------
								// Now cancel the original document
								// directly using our custom endpoint.
								// This avoids entering _cancel()
								// again and therefore prevents the
								// second confirmation/reason dialog.
								// ----------------------------------
								frappe.call({
									method: "yana_efris.api.efris_api.cancel_document",

									args: {
										doctype: me.doc.doctype,
										name: me.doc.name,
										cancellation_reason: cancellation_reason,
									},

									freeze: true,
									btn: btn,

									callback: (r) => {
										if (r.exc) {
											me.handle_save_fail(btn, on_error);
											return;
										}

										frappe.utils.play_sound("cancel");

										me.reload_doc();

										callback && callback();

										me.script_manager.trigger("after_cancel");
									},

									error: function () {
										me.handle_save_fail(btn, on_error);
									},
								});
							},

							error: function () {
								me.handle_save_fail(btn, on_error);
							},
						});
					},
				});

				reason_dialog.show();

				reason_dialog.fields_dict.cancellation_reason.$input.focus();
			});
		}

		d.show();
	};

	frappe.ui.form.Form.prototype._yana_efris_cancel_all_overridden = true;
};

frappe.after_ajax(function () {
	yana_efris.cancellation.setup_form_cancel_override();
	yana_efris.cancellation.setup_cancel_all_override();
});
