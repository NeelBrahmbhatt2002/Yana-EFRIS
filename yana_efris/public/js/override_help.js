(function () {
	const whatsappNumber = "YOUR_NUMBER"; // e.g. 256771234567
	const whatsappUrl = "https://wa.me/" + whatsappNumber;

	function addCustomHelp() {
		// Avoid duplicates
		if (document.querySelector("#yana-help-dropdown")) return;

		// The right-side navbar UL
		const navbarRight = document.querySelector("header .navbar-nav");

		if (!navbarRight) {
			setTimeout(addCustomHelp, 200);
			return;
		}

		// Find the avatar/profile item — the LAST nav-item
		const navItems = navbarRight.querySelectorAll("li.nav-item");
		const profileItem = navItems[navItems.length - 1]; // last <li>

		// Build our custom dropdown
		const li = document.createElement("li");
		li.id = "yana-help-dropdown";
		li.className = "nav-item dropdown";

		li.innerHTML = `
            <button class="btn btn-sm btn-link nav-link" data-toggle="dropdown">
                Help
            </button>
            <div class="dropdown-menu dropdown-menu-right">
                <a class="dropdown-item" href="${whatsappUrl}" target="_blank">
                    WhatsApp
                </a>
            </div>
        `;

		// Insert BEFORE the avatar item
		navbarRight.insertBefore(li, profileItem);

		console.log("✔ Yana ERP: Custom Help dropdown placed correctly before avatar.");
	}

	if (document.readyState === "loading") {
		document.addEventListener("DOMContentLoaded", addCustomHelp);
	} else {
		addCustomHelp();
	}
})();
