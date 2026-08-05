let yana_breadcrumb_timer = null;

frappe.router.on("change", () => {
	// Stop any previous polling
	if (yana_breadcrumb_timer) {
		clearInterval(yana_breadcrumb_timer);
	}

	let attempts = 0;

	yana_breadcrumb_timer = setInterval(() => {
		attempts++;

		const $container = $(".page-head .container");
		const $header = $container.find(".page-head-content");

		if (!$header.length) {
			if (attempts >= 30) {
				clearInterval(yana_breadcrumb_timer);
			}
			return;
		}

		render_yana_breadcrumb();

		// Render a few more times because Form refresh may rebuild the header.
		if (attempts >= 8) {
			clearInterval(yana_breadcrumb_timer);
		}
	}, 150);
});

function render_yana_breadcrumb() {
	const route = frappe.get_route();

	if (!route || !route.length) return;

	// Only List & Form
	if (!["List", "Form"].includes(route[0])) {
		$(".yana-breadcrumb").remove();
		return;
	}

	const $container = $(".page-head .container");
	const $header = $container.find(".page-head-content");

	if (!$container.length || !$header.length) return;

	// Remove only the breadcrumb inside this page
	$container.find(".yana-breadcrumb").remove();

	let module = "";
	let label = route[1] || "";
	let docname = "";

	// Get module from metadata
	try {
		const meta = frappe.get_meta(label);

		if (meta?.module) {
			module = meta.module;
		}
	} catch (e) {}

	// Fallback to breadcrumb cache
	if (!module) {
		const route_key = route.join("/");

		const breadcrumb =
			frappe.breadcrumbs.all?.[route_key] ||
			frappe.breadcrumbs.all?.[
				route_key.replace(/^Form\//, "List/").replace(/\/[^/]+$/, "/List")
			];

		if (breadcrumb) {
			module = breadcrumb.workspace || breadcrumb.module || "";
		}
	}

	if (route[0] === "Form") {
		docname = route[2] || "";
	}

	const parts = [];

	if (module) parts.push(module);
	if (label) parts.push(label);
	if (docname) parts.push(docname);

	if (!parts.length) return;

	const html = `
		<div class="yana-breadcrumb">
			${parts.join('<span class="sep">›</span>')}
		</div>
	`;

	$header.before(html);
}
