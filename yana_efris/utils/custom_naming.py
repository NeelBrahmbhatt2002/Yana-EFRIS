import frappe
from datetime import datetime
import re

# Transaction code for SAL invoices
TRANSACTION_CODES = {
    "Sales Invoice": "SAL",
    "Purchase Invoice": "PUR",
    "Payment Entry": "PAY",
    "Journal Entry": "REC",
}

def generate_document_series(doc, mode="pfi"):
    """
    mode = "pfi"   -> Generate Proforma naming series (PFI)
    mode = "efris" -> Generate EFRIS naming series (SAL)
    """

    company = doc.company or "DEF"
    company_code = company[:3].upper()

    # -----------------------------------------
    # PFI: Proforma Invoice Naming Series
    # -----------------------------------------
    if mode == "pfi":
        trans_code = "PFI"
        date_str = datetime.now().strftime("%Y%m%d")
        prefix = f"{company_code}{trans_code}{date_str}"

        # Fetch last PFI invoice ONLY
        last_doc = frappe.db.sql(
            """
            SELECT name FROM `tabSales Invoice`
            WHERE name LIKE %s
            ORDER BY creation DESC
            LIMIT 1
            """,
            (f"{prefix}%",),
            as_dict=True
        )

        if last_doc:
            name = last_doc[0]["name"]

            # Extract 4-digit sequence
            match = re.search(r'(\d{4})(?:-\d+)?$', name)
            if match:
                last_number = int(match.group(1))
            else:
                last_number = 0

            next_number = str(last_number + 1).zfill(4)
        else:
            next_number = "0001"

        doc.name = f"{prefix}{next_number}"
        return  # DONE


    # -----------------------------------------
    # SAL: EFRIS Invoice Naming Series
    # -----------------------------------------
    if mode == "efris":
        trans_code = TRANSACTION_CODES.get(doc.doctype, "SAL")

        # IMPORTANT → SAL must use today's date
        date_str = datetime.now().strftime("%Y%m%d")
        prefix = f"{company_code}{trans_code}{date_str}"

        # Fetch last SAL invoice for THIS DATE only
        last_doc = frappe.db.sql(
            """
            SELECT name FROM `tabSales Invoice`
            WHERE name LIKE %s
            ORDER BY creation DESC
            LIMIT 1
            """,
            (f"{prefix}%",),
            as_dict=True
        )

        if last_doc:
            name = last_doc[0]["name"]

            # Extract last 4-digit sequence
            match = re.search(r'(\d{4})(?:-\d+)?$', name)
            if match:
                last_number = int(match.group(1))
            else:
                last_number = 0

            next_number = str(last_number + 1).zfill(4)

        else:
            next_number = "0001"

        doc.name = f"{prefix}{next_number}"
        return


def custom_autoname(doc, method=None):
    generate_document_series(doc, mode="pfi")
