frappe.router.on("change", () => {
	wait_for_current_form();
});

function wait_for_current_form() {
	const route = frappe.get_route();

	// We only care about document forms
	if (!route || route[0] !== "Form" || !route[1] || !route[2]) {
		return;
	}

	const doctype = route[1];
	const name = route[2];

	let attempts = 0;
	const max_attempts = 20;

	const check = setInterval(() => {
		attempts++;

		if (
			cur_frm &&
			cur_frm.doc &&
			cur_frm.doc.doctype === doctype &&
			cur_frm.doc.name === name
		) {
			clearInterval(check);

			check_one_time_print(cur_frm);
			return;
		}

		if (attempts >= max_attempts) {
			clearInterval(check);
			console.log("One Time Print: Could not find current form.");
		}
	}, 100);
}

function check_one_time_print(frm) {
	// Do not check new/unsaved documents
	if (!frm.doc || frm.is_new()) {
		return;
	}

	frappe.call({
		method: "yana_efris.api.efris_api.check_document_printed",
		args: {
			doctype: frm.doc.doctype,
			name: frm.doc.name,
		},
		callback(r) {
			console.log("One Time Print:", frm.doc.doctype, frm.doc.name, r.message);
		},
	});
}
