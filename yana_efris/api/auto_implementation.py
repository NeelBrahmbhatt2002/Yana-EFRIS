import frappe
from frappe.utils import today


# =========================================================
# Company Implementation Automation
# =========================================================

DOCUMENT_NAMING_RULES = {
    "Quotation": "QT",
    "Pick List": "PL",
    "Delivery Note": "DN",
    "Sales Order": "SO",
    "Sales Invoice": "SI",
    "Purchase Order": "PO",
    "Purchase Receipt": "PR",
    "Purchase Invoice": "PI",
    "Material Request": "MR",
    "Journal Entry": "JE",
    "Work Order": "WO",
    "Stock Entry": "SE",
}


def add_company_to_current_fiscal_year(doc, method=None):
    """
    Automatically:
    1. Add newly created Company to the current Fiscal Year.
    2. Create Document Naming Rules for Sales and Purchase transactions.
    """

    current_date = today()

    # -----------------------------------------------------
    # 1. Find Current Fiscal Year
    # -----------------------------------------------------

    fiscal_year = frappe.db.get_value(
        "Fiscal Year",
        {
            "year_start_date": ["<=", current_date],
            "year_end_date": [">=", current_date],
            "disabled": 0,
        },
        "name",
    )

    if not fiscal_year:
        frappe.log_error(
            title="Fiscal Year Not Found",
            message=(
                f"Could not find an active Fiscal Year for Company "
                f"{doc.name} on {current_date}."
            ),
        )
        return

    # -----------------------------------------------------
    # 2. Add Company to Fiscal Year
    # -----------------------------------------------------

    fiscal_year_doc = frappe.get_doc("Fiscal Year", fiscal_year)

    company_exists = any(
        row.company == doc.name
        for row in fiscal_year_doc.companies
    )

    if not company_exists:
        fiscal_year_doc.append(
            "companies",
            {
                "company": doc.name
            }
        )

        fiscal_year_doc.save(ignore_permissions=True)

    # -----------------------------------------------------
    # 3. Create Document Naming Rules
    # -----------------------------------------------------
    if doc.custom_create_auto_naming_series:
        create_document_naming_rules(doc)


def create_document_naming_rules(company):
    """
    Create Document Naming Rules for Sales and Purchase transactions.
    """

    company_abbreviation = company.abbr

    if not company_abbreviation:
        frappe.log_error(
            title="Company Abbreviation Missing",
            message=(
                f"Could not create Document Naming Rules for "
                f"{company.name} because the company abbreviation is missing."
            ),
        )
        return

    for document_type, document_prefix in DOCUMENT_NAMING_RULES.items():

        # -------------------------------------------------
        # Naming format:
        #
        # Company Abbreviation
        # + Document Prefix
        # + Year
        # + Month
        # + Date
        #
        # Example:
        # NESCOSAL202609240001
        # -------------------------------------------------

        prefix = f"{company_abbreviation}{document_prefix}.YYYY.MM.DD."

        # -------------------------------------------------
        # Check whether an equivalent rule already exists
        # -------------------------------------------------

        if document_naming_rule_exists(
            document_type=document_type,
            company=company.name,
            prefix=prefix,
        ):
            continue

        naming_rule = frappe.get_doc(
            {
                "doctype": "Document Naming Rule",
                "document_type": document_type,
                "disabled": 0,
                "priority": 0,
                "prefix": prefix,
                "counter": 0,
                "prefix_digits": 4,
            }
        )

        naming_rule.append(
            "conditions",
            {
                "field": "company",
                "condition": "=",
                "value": company.name,
            }
        )

        naming_rule.insert(ignore_permissions=True)


def document_naming_rule_exists(document_type, company, prefix):
    """
    Check whether a matching Document Naming Rule already exists.
    """

    rules = frappe.get_all(
        "Document Naming Rule",
        filters={
            "document_type": document_type,
            "prefix": prefix,
            "disabled": 0,
        },
        pluck="name",
    )

    for rule_name in rules:

        rule = frappe.get_cached_doc(
            "Document Naming Rule",
            rule_name
        )

        for condition in rule.conditions:

            if (
                condition.field == "company"
                and condition.condition == "="
                and condition.value == company
            ):
                return True

    return False




def add_company_to_mode_of_payments(doc, method=None):
    """
    Add Company to required Modes of Payment after
    ERPNext has completed its default account setup.
    """

    company = doc.name

    # Fetch the latest saved Default Cash Account
    cash_account = frappe.db.get_value(
        "Company",
        company,
        "default_cash_account"
    )

    if not cash_account:
        frappe.log_error(
            title="Mode of Payment Automation",
            message=f"Default Cash Account not found for Company: {company}"
        )
        return

    mode_of_payments = [
        "Cash",
        "Cheque",
        "MM",
        "Credit Card",
        "Credit Sales",
        "EFT",
        "MTN"
    ]

    for mode_name in mode_of_payments:

        if not frappe.db.exists("Mode of Payment", mode_name):
            continue

        savepoint = f"mop_{frappe.scrub(mode_name)}"

        try:
            frappe.db.savepoint(savepoint)

            mode_doc = frappe.get_doc(
                "Mode of Payment",
                mode_name,
                for_update=True
            )

            existing_row = next(
                (
                    row for row in mode_doc.accounts
                    if row.company == company
                ),
                None
            )

            if existing_row:
                if not existing_row.default_account:
                    existing_row.default_account = cash_account
                    mode_doc.save(ignore_permissions=True)

                continue

            mode_doc.append("accounts", {
                "company": company,
                "default_account": cash_account
            })

            mode_doc.save(ignore_permissions=True)

        except Exception:
            frappe.db.rollback(save_point=savepoint)

            frappe.log_error(
                title=f"Mode of Payment Error: {mode_name}",
                message=frappe.get_traceback()
            )
