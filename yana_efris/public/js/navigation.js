const module_map = {
	Quotation: "sales-dashboard",
	"Sales Order": "sales-dashboard",
	"Sales Invoice": "sales-dashboard",
	"Delivery Note": "sales-dashboard",
	Customer: "sales-dashboard",

	"Purchase Order": "purchase-dashboard",
	"Purchase Invoice": "purchase-dashboard",
	Supplier: "purchase-dashboard",
	"Purchase Receipts": "purchase-dashboard",

	// Item: "home",
	// "Stock Entry": "home",

	// "Payment Entry": "home",
	// "Journal Entry": "home",
};

frappe.router.on("change", () => {
	const route = frappe.get_route();

	if (route[0] === "Form") {
		setTimeout(add_form_back_button, 500);
	}

	if (route[0] === "List") {
		setTimeout(add_list_back_button, 500);
	}
});

// function add_form_back_button() {
// 	const frm = cur_frm;

// 	if (!frm || !frm.page) return;

// 	const module = module_map[frm.doctype];
// 	if (!module) return;

// 	// Avoid duplicates
// 	if (
// 		frm.page.inner_toolbar &&
// 		frm.page.inner_toolbar.find("button:contains('← Back')").length
// 	) {
// 		return;
// 	}

// 	frm.add_custom_button(__("← Back"), () => {
// 		frappe.set_route("List", frm.doctype);
// 	});
// }

// function add_list_back_button() {
// 	const list = cur_list;

// 	if (!list || !list.page) return;

// 	const module = module_map[list.doctype];
// 	if (!module) return;

// 	if (
// 		list.page.inner_toolbar &&
// 		list.page.inner_toolbar.find("button:contains('← Go Back')").length
// 	) {
// 		return;
// 	}

// 	list.page.add_inner_button(__("← Go Back"), () => {
// 		frappe.set_route(module);
// 	});
// }

function add_form_back_button() {
	const frm = cur_frm;

	if (!frm || !frm.page) return;

	// Remove existing button
	$(".yana-left-form-back").remove();
	const is_mobile = window.innerWidth <= 768;

	const btn = $(`
		<button class="btn btn-default btn-sm yana-left-form-back">
			        <span class="yana-back-arrow">←</span>
        <span class="yana-back-text"> Back</span>
		</button>
	`);

	// btn.on("click", () => {
	// 	if (module_map.hasOwnProperty(frm.doctype)) {
	// 		frappe.set_route("List", frm.doctype);
	// 	} else {
	// 		frappe.set_route("home");
	// 	}
	// });

	btn.on("click", () => {
		const doctype = frm.doctype;

		frappe.set_route("List", doctype);

		// Give the router a moment to resolve the route
		setTimeout(() => {
			const route = frappe.get_route();

			// If we're still on the same form, the list route wasn't available
			if (route[0] === "Form" && route[1] === doctype) {
				frappe.set_route("home");
			}
		}, 300);
	});

	frm.page.wrapper.find(".page-head h3, .page-head .title-text").first().before(btn);
}

function add_list_back_button() {
	const list = cur_list;

	if (!list || !list.page) return;

	const module = module_map[list.doctype] || "home";
	// if (!module) return;

	// Remove existing button
	$(".yana-left-back").remove();
	const is_mobile = window.innerWidth <= 768;

	const btn = $(`
		<button class="btn btn-default btn-sm yana-left-back">
			<span class="yana-back-arrow">←</span>
        <span class="yana-back-text"> Back</span>
		</button>
	`);

	btn.on("click", () => {
		frappe.set_route(module);
	});

	list.page.wrapper.find(".page-head h3, .page-head .title-text").first().before(btn);
}
