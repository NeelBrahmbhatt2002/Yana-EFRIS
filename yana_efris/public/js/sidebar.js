frappe.provide("custom.sidebar");

$(document).ready(function () {
	/* ------------------------------------------------------------
	 * 1. WAIT UNTIL ERPNext SIDEBAR IS RENDERED
	 * ------------------------------------------------------------ */
	function wait_for_sidebar(callback) {
		const observer = new MutationObserver((mutations, obs) => {
			const $public_section = $(
				'div.standard-sidebar-section.nested-container[data-title="Public"]'
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

			const $container = $(this).closest(".sidebar-item-container");
			const $children = $container.children(".sidebar-child-item");
			const $icon = $(this).find(".collapse-icon");

			$children.toggleClass("hidden");

			// Toggle arrow
			if ($children.hasClass("hidden")) {
				$icon.attr("href", "#es-line-down");
			} else {
				$icon.attr("href", "#es-line-up");
			}
		});
	}

	/* ------------------------------------------------------------
	 * 2. CREATE SIDEBAR ITEM HTML (DUMMY)
	 * ------------------------------------------------------------ */
	function create_sidebar_item({ label, link, icon }) {
		return `
        <div class="sidebar-item-container"
             item-parent="My Custom Menu"
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
        </div>
    `;
	}

	/* ------------------------------------------------------------
	 * 3. CREATE A CUSTOM CATEGORY WITH CHILD LINKS
	 * ------------------------------------------------------------ */
	function create_custom_category() {
		return `
    <div class="sidebar-item-container is-draggable"
         data-custom-sidebar="1"
         item-name="My Custom Menu"
         item-public="1"
         item-is-hidden="0">

        <!-- Parent -->
        <div class="desk-sidebar-item standard-sidebar-item">
            <a class="item-anchor" title="My Custom Menu">
                <span class="sidebar-item-icon" item-icon="star">
                    <svg class="icon icon-md">
                        <use href="#icon-star"></use>
                    </svg>
                </span>
                <span class="sidebar-item-label">My Custom Menu</span>
            </a>

            <!-- Collapse control -->
            <div class="sidebar-item-control">
                <button class="btn-reset collapse-btn drop-icon" title="Collapse / Expand">
                    <svg class="es-icon es-line icon-sm">
                        <use class="collapse-icon" href="#es-line-down"></use>
                    </svg>
                </button>
            </div>
        </div>

        <!-- 🔑 CHILD ITEMS MUST BE HIDDEN INITIALLY -->
        <div class="sidebar-child-item nested-container hidden">

            ${create_sidebar_item({
				label: "Dummy Page One",
				link: "/app/todo/new-todo",
				icon: "edit",
			})}

            ${create_sidebar_item({
				label: "Dummy Page Two",
				link: "/app/user",
				icon: "users",
			})}

            ${create_sidebar_item({
				label: "External Link",
				link: "https://example.com",
				icon: "link",
			})}

        </div>
    </div>
    `;
	}

	/* ------------------------------------------------------------
	 * 4. INJECT INTO EXISTING SIDEBAR (SAFE)
	 * ------------------------------------------------------------ */
	function inject_sidebar_items() {
		wait_for_sidebar(($public_section) => {
			// ❌ Prevent duplicate insertions
			if ($public_section.find('[data-custom-sidebar="1"]').length) {
				return;
			}

			const custom_html = create_custom_category();

			// ✅ Append at bottom of Public section
			$public_section.append(custom_html);

			bind_custom_sidebar_toggle($public_section);
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
