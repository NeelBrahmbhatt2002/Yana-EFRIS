frappe.provide("custom.sidebar");

function hide_frappe_workspaces() {
	// Hide only TOP-LEVEL Frappe workspace items
	$(".standard-sidebar-section")
		.find(".sidebar-item-container")
		.filter(function () {
			const hasParent = $(this).attr("item-parent");
			const isCustom = $(this).attr("data-custom-sidebar") === "1";

			// Hide only top-level non-custom items
			return !hasParent && !isCustom;
		})
		.hide();
}

const MENU_ROLE_MAP = {
	"Item Master": ["Item Manager", "Stock User", "Stock Manager"],

	Inventory: ["Stock User", "Stock Manager"],

	Purchase: ["Purchase User", "Purchase Manager", "Purchase Master Manager"],

	Sale: ["Sales User", "Sales Manager", "Sales Master Manager"],

	Accounting: ["Accounts User", "Accounts Manager"],

	Costing: ["Accounts User", "Accounts Manager"],

	Banking: ["Accounts User", "Accounts Manager"],

	"Multi Currency": ["Accounts User", "Accounts Manager", "Sales User", "Sales Manager"],

	Manufacturing: ["Manufacturing User", "Manufacturing Manager"],

	CRM: ["Sales User", "Sales Manager", "Sales Master Manager"],

	Projects: ["Projects User", "Projects Manager"],

	"Subscription Management": ["System Manager"],

	Payments: ["Accounts User", "Accounts Manager", "Sales User", "Sales Manager"],

	Assets: ["Accounts User", "Accounts Manager"],

	"HR & Payroll": ["HR User", "HR Manager"],

	Reports: ["Report Manager"],

	Utilities: ["System Manager"],
};

function has_menu_access(menuTitle) {
	// System Manager sees everything
	if (frappe.user_roles.includes("System Manager")) {
		return true;
	}

	const allowedRoles = MENU_ROLE_MAP[menuTitle];

	// If no mapping exists, show menu
	if (!allowedRoles) {
		return true;
	}

	return allowedRoles.some((role) => frappe.user_roles.includes(role));
}

const CUSTOM_MENUS = [
	{
		title: "Item Master",
		icon: "tag",
		items: [
			{ label: "Items", link: "/app/item", icon: "" },
			{ label: "Item Groups", link: "/app/item-group", icon: "" },
			{ label: "Price List", link: "/app/price-list", icon: "" },
			{ label: "UOM", link: "/app/uom", icon: "" },
		],
	},
	{
		title: "Inventory",
		icon: "stock",
		items: [
			{ label: "Stock Ledger", link: "/app/stock-ledger", icon: "" },
			{ label: "Stock Entry", link: "/app/stock-entry", icon: "" },
			{ label: "Inventory Adjustments", link: "/app/stock-reconciliation", icon: "" },
			{ label: "Packages", link: "/app/package", icon: "" },
			{ label: "Shipments", link: "/app/shipment", icon: "" },
		],
	},
	{
		title: "Purchase",
		icon: "buying",
		items: [
			// { label: "Purchase Dashboard", link: "/app/purchase-dashboard", icon: "" },
			{ label: "Suppliers", link: "/app/supplier", icon: "" },
			{ label: "Purchase Orders", link: "/app/purchase-order", icon: "" },
			{ label: "Purchase Invoices", link: "/app/purchase-invoice", icon: "" },
			{ label: "Purchase Receipts", link: "/app/purchase-receipt", icon: "" },
		],
	},
	{
		title: "Sale",
		icon: "star",
		items: [
			{ label: "Sales Dashboard", link: "/app/sales-dashboard", icon: "" },
			{ label: "Point of Sale", link: "/pos", icon: "" },
			{ label: "Customers", link: "/app/customer", icon: "" },
			{ label: "Quotes", link: "/app/quotation", icon: "" },
			{ label: "Sales Orders", link: "/app/sales-order", icon: "" },
			{ label: "Invoices", link: "/app/sales-invoice", icon: "" },
		],
	},
];

const CUSTOM_MENUS_2 = [
	{
		title: "Accounting",
		icon: "accounting",
		items: [
			{ label: "Journal Entry", link: "/app/journal-entry", icon: "" },
			{ label: "Chart Of Accounts", link: "/app/account/view/tree", icon: "" },
		],
	},
	{
		title: "Costing",
		icon: "expenses",
		items: [
			{ label: "Chart of Cost Centers", link: "/app/cost-center", icon: "" },
			{ label: "Budget", link: "/app/budget", icon: "" },
			{ label: "Accounting Dimension", link: "/app/accounting-dimension", icon: "" },
			{ label: "Cost Center Allocation", link: "/app/cost-center-allocation", icon: "" },
			{
				label: "Budget Variance Report",
				link: "/app/query-report/Budget Variance Report",
				icon: "",
			},
			{ label: "Monthly Distribution", link: "/app/monthly-distribution", icon: "" },
		],
	},
	{
		title: "Banking",
		icon: "income",
		items: [
			{ label: "Bank", link: "/app/bank", icon: "" },
			{ label: "Bank Account", link: "/app/bank-account", icon: "" },
			{ label: "Bank Clearance", link: "/app/bank-clearance", icon: "" },
			{ label: "Bank Reconciliation Tool", link: "/app/bank-reconciliation-tool", icon: "" },
			{
				label: "Bank Reconciliation Statement",
				link: "/app/query-report/Bank Reconciliation Statement",
				icon: "",
			},
		],
	},
	{
		title: "Multi Currency",
		icon: "workflow",
		items: [
			{ label: "Currency", link: "/app/currency", icon: "" },
			{ label: "Currency Exchange", link: "/app/currency-exchange", icon: "" },
			{
				label: "Exchange Rate Revaluation",
				link: "/app/exchange-rate-revaluation",
				icon: "",
			},
		],
	},
	{
		title: "Manufacturing",
		icon: "organization",
		items: [
			{ label: "Work Order", link: "/app/work-order", icon: "" },
			{ label: "Production Plan", link: "/app/production-plan", icon: "" },
			{ label: "Stock Entry", link: "/app/stock-entry", icon: "" },
			{ label: "Job Card", link: "/app/job-card", icon: "" },
			{ label: "Downtime Entry", link: "/app/downtime-entry", icon: "" },
		],
	},
];

const CUSTOM_MENUS_1 = [
	{
		title: "CRM",
		icon: "crm",
		items: [
			{ label: "Lead", link: "/app/lead", icon: "" },
			{ label: "Opportunity", link: "/app/opportunity", icon: "" },
			{ label: "Customer", link: "/app/customer", icon: "" },
			{ label: "Contract", link: "/app/contract", icon: "" },
			{ label: "Appointment", link: "/app/appointment", icon: "" },
			{ label: "Newsletter", link: "/app/newsletter", icon: "" },
			{ label: "Communication", link: "/app/communication", icon: "" },
		],
	},
	{
		title: "Projects",
		icon: "project",
		items: [
			{ label: "Project", link: "/app/project", icon: "" },
			{ label: "Task", link: "/app/task", icon: "" },
			{ label: "Project Template", link: "/app/project-template", icon: "" },
			{ label: "Project Type", link: "/app/project-type", icon: "" },
			{ label: "Project Update", link: "/app/project-update", icon: "" },
		],
	},
	{
		title: "Subscription Management",
		icon: "tag",
		items: [
			{ label: "Subscription Plan", link: "/app/subscription-plan", icon: "" },
			{ label: "Subscription", link: "/app/subscription", icon: "" },
			{ label: "Subscription Settings", link: "/app/subscription-settings", icon: "" },
		],
	},
];

// Checking logic for home route.
function is_home_route() {
	const path = window.location.pathname;
	return path === "/app/home";
}

// Logic to reset all the dropdowns
function reset_all_dropdowns() {
	$(".sidebar-child-item").addClass("hidden");
	$(".collapse-icon").attr("href", "#es-line-down");
}

$(document).ready(function () {
	console.log("This console should work");
	/* ------------------------------------------------------------
	 * 1. WAIT UNTIL ERPNext SIDEBAR IS RENDERED
	 * ------------------------------------------------------------ */
	function wait_for_sidebar(callback) {
		const observer = new MutationObserver((mutations, obs) => {
			const $public_section = $(
				'div.standard-sidebar-section.nested-container[data-title="Public"]',
			);

			if ($public_section.length) {
				obs.disconnect();
				callback($public_section);
			}
		});

		observer.observe(document.body, { childList: true, subtree: true });
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

	/* ------------------------------------------------------------
	 * 2. CREATE SIDEBAR ITEM HTML (DUMMY)
	 * ------------------------------------------------------------ */
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

	function create_home_link(label, link, icon) {
		// if (!has_menu_access(label) && label !== "Dashboard") {
		// 	return "";
		// }
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

	function create_menu_group(menu) {
		// if (!has_menu_access(menu.title)) {
		// 	return "";
		// }
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

	function is_any_dropdown_open() {
		return (
			$(".sidebar-child-item").filter(function () {
				return !$(this).hasClass("hidden");
			}).length > 0
		);
	}

	function apply_optional_polishing() {
		const path = window.location.pathname;

		reset_all_dropdowns();
		// $(".desk-sidebar-item").removeClass("selected");

		// Highlight Home when active
		// if (path === "/app/home") {
		// 	console.log("Pathname is", path);
		// 	$(".sidebar-item-container[item-name='Home']")
		// 		.find(".desk-sidebar-item")
		// 		.addClass("selected");
		// }

		// Auto-expand parent menu if a child page is active
		$(".sidebar-item-container[item-parent]").each(function () {
			const href = $(this).find("a.item-anchor").attr("href");
			if (href === path) {
				const parentName = $(this).attr("item-parent");
				const $parent = $(`.sidebar-item-container[item-name='${parentName}']`);
				// $(".sidebar-item-container[item-name='Home']")
				// 	.find(".desk-sidebar-item")
				// 	.removeClass("selected");

				$parent.find(".sidebar-child-item").removeClass("hidden");
				$parent.find(".collapse-icon").attr("href", "#es-line-up");
			}
		});
	}

	/* ------------------------------------------------------------
	 * 4. INJECT INTO EXISTING SIDEBAR (SAFE)
	 * ------------------------------------------------------------ */
	function inject_sidebar_items() {
		wait_for_sidebar(($public_section) => {
			// Prevent duplicates
			if ($public_section.find('[data-custom-sidebar="1"]').length) {
				return;
			}

			$public_section.append(create_home_link("My Workspace", "/app/home", "dashboard"));

			CUSTOM_MENUS.forEach((menu) => {
				$public_section.append(create_menu_group(menu));
			});

			$public_section.append(
				create_home_link("Payments", "/app/payment-entry", "number-card"),
			);

			CUSTOM_MENUS_2.forEach((menu) => {
				$public_section.append(create_menu_group(menu));
			});

			$public_section.append(create_home_link("Assets", "/app/assets", "assets"));

			$public_section.append(create_home_link("HR & Payroll", "/app/hr", "hr"));

			// $public_section.append(create_home_link("Payroll", "/app/payroll", "money-coins-1"));

			CUSTOM_MENUS_1.forEach((menu) => {
				$public_section.append(create_menu_group(menu));
			});

			$public_section.append(create_home_link("Reports", "/app/reports", "chart"));

			$public_section.append(create_home_link("Utilities", "/app/tools", "tool"));

			bind_custom_sidebar_toggle($public_section);

			hide_frappe_workspaces();

			apply_optional_polishing();
		});
	}

	/* ------------------------------------------------------------
	 * 5. RUN ON LOAD & SIDEBAR REFRESH
	 * ------------------------------------------------------------ */
	inject_sidebar_items();

	// When workspace changes or sidebar reloads
	$(document).on("page-change sidebar-refresh", function () {
		inject_sidebar_items();
	});
});
