frappe.provide("custom.list_sidebar");

function is_list_route() {
	const route = frappe.get_route();

	console.log("Route value:", route);

	if (!route) return false;

	return route[0] === "List";
}

console.log("✅ list_sidebar_override.js loaded");

// function wait_for_list_sidebar(callback) {
// 	console.log("⏳ Waiting for list sidebar...");

// 	const interval = setInterval(() => {
// 		const $sidebar = $(".layout-main .layout-side-section").first();

// 		console.log("Checking sidebar...", $sidebar.length);

// 		if ($sidebar.length) {
// 			console.log("✅ Sidebar FOUND");
// 			clearInterval(interval);
// 			callback($sidebar);
// 		}
// 	}, 300);
// }

function create_home_link(label, link, icon) {
	return `
	<div class="sidebar-item-container is-draggable"
		 data-custom-sidebar="1"
		 item-name="${label}"
		 item-public="1"
		 item-is-hidden="0">

		<div class="desk-sidebar-item standard-sidebar-item">
			<a href="${link}" class="item-anchor" title="${label}">
				<span class="sidebar-item-icon" item-icon="${icon}">
					<svg class="icon icon-md">
						<use href="#icon-${icon}"></use>
					</svg>
				</span>
				<span class="sidebar-item-label">${label}</span>
			</a>
		</div>
	</div>`;
}

function create_sidebar_item(parent, { label, link, icon }) {
	return `
	<div class="sidebar-item-container"
		 item-parent="${parent}"
		 item-name="${label}"
		 item-public="1"
		 item-is-hidden="0">
		<div class="desk-sidebar-item standard-sidebar-item">
			<a href="${link}" class="item-anchor" title="${label}">
				<span class="sidebar-item-icon" item-icon="${icon}">
					<svg class="icon icon-md">
						<use href="#icon-${icon}"></use>
					</svg>
				</span>
				<span class="sidebar-item-label">${label}</span>
			</a>
		</div>
	</div>`;
}

function create_menu_group(menu) {
	const children = menu.items.map((item) => create_sidebar_item(menu.title, item)).join("");

	return `
	<div class="sidebar-item-container is-draggable"
		 data-custom-sidebar="1"
		 item-name="${menu.title}"
		 item-public="1"
		 item-is-hidden="0">

		<div class="desk-sidebar-item standard-sidebar-item">
			<a class="item-anchor" title="${menu.title}">
				<span class="sidebar-item-icon" item-icon="${menu.icon}">
					<svg class="icon icon-md">
						<use href="#icon-${menu.icon}"></use>
					</svg>
				</span>
				<span class="sidebar-item-label">${menu.title}</span>
			</a>

			<div class="sidebar-item-control">
				<button class="btn-reset collapse-btn drop-icon">
					<svg class="es-icon es-line icon-sm">
						<use class="collapse-icon" href="#es-line-down"></use>
					</svg>
				</button>
			</div>
		</div>

		<div class="sidebar-child-item nested-container hidden">
			${children}
		</div>
	</div>`;
}

function bind_custom_sidebar_toggle($root) {
	$root.on("click", ".collapse-btn", function (e) {
		e.preventDefault();
		e.stopPropagation();

		const $current = $(this).closest(".sidebar-item-container");
		const $children = $current.children(".sidebar-child-item");
		const $icon = $(this).find(".collapse-icon");

		const isOpen = !$children.hasClass("hidden");

		// 🔒 CLOSE ALL DROPDOWNS FIRST (Accordion behavior)
		reset_all_dropdowns();

		// If it was closed, open it
		if (!isOpen) {
			$children.removeClass("hidden");
			$icon.attr("href", "#es-line-up");
		}

		// if (is_any_dropdown_open()) {
		// 	$(".sidebar-item-container[item-name='Home']")
		// 		.find(".desk-sidebar-item")
		// 		.removeClass("selected");
		// } else if (is_home_route()) {
		// 	// All closed + on home → Home active
		// 	$(".sidebar-item-container[item-name='Home']")
		// 		.find(".desk-sidebar-item")
		// 		.addClass("selected");
		// } else {
		// 	$(".sidebar-item-container[item-name='Home']")
		// 		.find(".desk-sidebar-item")
		// 		.removeClass("selected");
		// }
	});
}

function render_custom_sidebar($parent) {
	console.log("🚀 Rendering custom sidebar");

	$parent.find(".custom-list-sidebar").remove();
	$parent.find(".list-sidebar").remove();

	const $wrapper = $(`
		<div class="desk-sidebar list-unstyled sidebar-menu custom-list-sidebar">
			<div class="standard-sidebar-section nested-container"></div>
		</div>
	`);

	$parent.append($wrapper);

	const $section = $wrapper.find(".standard-sidebar-section");

	$section.append(create_home_link("Dashboard", "/app/home", "dashboard"));

	CUSTOM_MENUS.forEach((menu) => {
		$section.append(create_menu_group(menu));
	});

	$section.append(create_home_link("Assets", "/app/assets", "assets"));

	CUSTOM_MENUS_1.forEach((menu) => {
		$section.append(create_menu_group(menu));
	});

	$section.append(create_home_link("Reports", "/app/reports", "chart"));
	$section.append(create_home_link("Utilities", "/app/tools", "tool"));

	bind_custom_sidebar_toggle($section);

	console.log("✅ Sidebar rendered fresh");
}

// function init_list_sidebar_override() {
// 	console.log("👉 init_list_sidebar_override called");
// 	if (!is_list_route()) {
// 		console.log("❌ Not a list route");
// 		return;
// 	}

// 	console.log("✅ This is a LIST route");

// 	// wait_for_list_sidebar(($sidebar) => {
// 	// 	console.log("🎯 Sidebar detected:", $sidebar);
// 	// 	render_custom_sidebar($sidebar);
// 	// });
// }

// Run on route change
// frappe.router.on("change", () => {
// 	console.log("🔥 Route changed");
// 	setTimeout(() => {
// 		init_list_sidebar_override();
// 	}, 150);
// });

// // Initial load
// $(document).on("list-rendered", function () {
// 	console.log("🔄 List rendered event");
// 	init_list_sidebar_override();
// });

// Override ONLY the sidebar method
frappe.after_ajax(() => {
	console.log("🔥 Applying ListView sidebar override");

	if (!frappe.views || !frappe.views.ListView) {
		console.log("❌ ListView not available yet");
		return;
	}

	const original = frappe.views.ListView.prototype.setup_sidebar;

	frappe.views.ListView.prototype.setup_sidebar = function () {
		console.log("🚫 Overriding default sidebar");

		// DO NOT call original → prevents filter sidebar

		const $sidebar = $(this.page.sidebar);

		if ($sidebar && $sidebar.length) {
			$sidebar.empty();
		}

		setTimeout(() => {
			const $target = $(".layout-main .layout-side-section").first();

			if ($target.length) {
				console.log("🚀 Injecting custom sidebar (final)");
				render_custom_sidebar($target);
			}
		}, 50);
	};
});
