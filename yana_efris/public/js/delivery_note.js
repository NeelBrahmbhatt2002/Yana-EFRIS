frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;

		if (frm.doc.items?.length) {
			console.log(frm.doc.items[0]);
			let sales_order = frm.doc.items[0].against_sales_order;
			console.log("Sales Order:", sales_order);

			if (sales_order) {
				frm.set_value("custom_reference_document_number", sales_order);
				console.log("Sales Order Set");
			}
		}
	},
});
