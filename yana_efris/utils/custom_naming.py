import frappe
from datetime import datetime
import re

# Transaction codes for SAL invoices
TRANSACTION_CODES = {
    "Sales Invoice": "SAL",
    "Purchase Invoice": "PUR",
    "Payment Entry": "PAY",
    "Journal Entry": "REC",
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
