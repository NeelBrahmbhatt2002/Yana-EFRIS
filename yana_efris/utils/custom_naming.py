import frappe
from datetime import datetime
import re

# Transaction codes for SAL invoices
TRANSACTION_CODES = {
    "Sales Invoice": "SAL",
    "Purchase Invoice": "PUR",
    "Payment Entry": "PAY",
    # "Journal Entry": "REC",
}

def _get_next_number(prefix):
    """
    Returns next 4-digit sequence for invoices matching prefix.
    Ignores amended invoices like ...0003-1 or ...0003-2.
    Ensures numeric ordering and amendment safety.
    """

    last_doc = frappe.db.sql(
        """
        SELECT name FROM `tabSales Invoice`
        WHERE name LIKE %s
          AND name REGEXP %s
        ORDER BY CAST(SUBSTRING(name, -4) AS UNSIGNED) DESC
        LIMIT 1
        """,
        (f"{prefix}%", rf"{prefix}[0-9]{{4}}$"),
        as_dict=True,
    )

    if last_doc:
        name = last_doc[0]["name"]
        # Extract last 4 digits safely
        match = re.search(r'(\d{4})$', name)
        last_number = int(match.group(1)) if match else 0
        return str(last_number + 1).zfill(4)

    return "0001"


def generate_document_series(doc, mode="pfi"):
    """
    mode = "pfi"   -> Generate Proforma naming series (PFI)
    mode = "efris" -> Generate final EFRIS naming series (SAL)
    """

    company = doc.company or "DEF"
    company_code = frappe.db.get_value("Company", company, "abbr") or company[:3].upper()
    company_code = company_code.upper()

    # -----------------------------------
    # 1️⃣ PFI NAMING SERIES (Proforma)
    # -----------------------------------
    if mode == "pfi":
        date_str = datetime.now().strftime("%Y%m%d")
        trans_code = "PFI"
        prefix = f"{company_code}{trans_code}{date_str}"

        next_number = _get_next_number(prefix)
        doc.name = f"{prefix}{next_number}"
        return

    # -----------------------------------
    # 2️⃣ SAL NAMING SERIES (EFRIS)
    # -----------------------------------
    if mode == "efris":
        # EFRIS requirement — MUST use TODAY's date
        date_str = datetime.now().strftime("%Y%m%d")
        trans_code = TRANSACTION_CODES.get(doc.doctype, "SAL")
        prefix = f"{company_code}{trans_code}{date_str}"

        next_number = _get_next_number(prefix)
        doc.name = f"{prefix}{next_number}"
        return


def custom_autoname(doc, method=None):
    """Default autoname hook: Always PFI for new invoices."""
    generate_document_series(doc, mode="pfi")

def set_manual_name(doc, method=None):

    # Skip doctypes that use custom auto naming
    if doc.doctype in ["Sales Invoice"]:
        return
    
    manual = getattr(doc, "custom_document_name", None)

    if not manual:
        return

    if not doc.is_new():
        frappe.throw("Custom Document Name can only be set on new documents before saving.")

    company_abbr = frappe.db.get_value("Company", doc.company, "abbr")
    if not company_abbr:
        frappe.throw(f"Company abbreviation not defined for {doc.company}.")

    # Auto uppercase
    manual = manual.strip().upper()

    # Sanitize
    safe_name = sanitize(manual)

    # Enforce prefix
    if not safe_name.startswith(company_abbr.upper()):
        frappe.throw(
            f"Document Name must start with company abbreviation '{company_abbr.upper()}'. "
            "Example: MHS-INV-0001"
        )

    # Check duplicates
    if frappe.db.exists(doc.doctype, safe_name):
        frappe.throw(f"Document name '{safe_name}' already exists. Please choose another.")

    doc.name = safe_name


# def sanitize(value):
#     sanitized = re.sub(r"[^A-Z0-9\-_]", "", value)
#     if not sanitized:
#         frappe.throw("Invalid Document Name. Only letters, numbers, dash (-) and underscore (_) are allowed.")
#     return sanitized

def sanitize(value):
    # Detect any invalid characters
    if re.search(r"[^A-Z0-9\-_]", value):
        frappe.throw("Invalid Document Name. Only letters, numbers, dash (-) and underscore (_) are allowed.")

    # Return unchanged, since it's already valid
    return value


