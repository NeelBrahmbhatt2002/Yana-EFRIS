import frappe
from frappe.model.naming import make_autoname
from datetime import datetime

# Transaction type short codes
TRANSACTION_CODES = {
    "Sales Invoice": "SAL",
    "Purchase Invoice": "PUR",
    "Payment Entry": "PAY",
    "Journal Entry": "REC",  # you can change this if needed
}

def generate_document_series(doc, method):
    """
    Auto-generate document name as CCCTTTYYYYMMDDXXXX
    Example: MERSAL202511110001
    """
    company = doc.company or "DEF"
    company_code = company[:3].upper()
    trans_code = TRANSACTION_CODES.get(doc.doctype, "GEN")

    date_str = datetime.now().strftime("%Y%m%d")
    prefix = f"{company_code}{trans_code}{date_str}"

    # Fetch last used document for the same company and type
    last_doc = frappe.db.sql(
        f"""
        SELECT name FROM `tab{doc.doctype}`
        WHERE name LIKE %s
        ORDER BY creation DESC
        LIMIT 1
        """,
        (f"{prefix}%",),
        as_dict=True,
    )

    if last_doc:
        last_number = int(last_doc[0]["name"][-4:])
        next_number = str(last_number + 1).zfill(4)
    else:
        next_number = "0001"

    doc.name = f"{prefix}{next_number}"
