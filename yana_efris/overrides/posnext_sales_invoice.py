import frappe
from frappe import _
from frappe.utils import cint

def validate(doc, method=None):
    """
    Override POSNext validate
    """

    apply_tax_inclusive(doc)

    try:
        from pos_next.api.sales_invoice_hooks import auto_assign_loyalty_program_on_invoice
        auto_assign_loyalty_program_on_invoice(doc)
    except Exception:
        pass


def apply_tax_inclusive(doc):

    # 🚨 ONLY skip POS invoices
    if doc.get("is_pos"):
        return

    frappe.log_error("🔥 YANA PATCH RUNNING", f"Invoice: {doc.name}")

    for tax in doc.get("taxes", []):
        if "VAT" in (tax.account_head or ""):
            tax.included_in_print_rate = 1

    # ❗ DO NOT call calculate_taxes_and_totals here