import frappe
from frappe import _
from frappe.utils import now_datetime
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error

def get_einvoice_json(self, sales_invoice):
    """
    Build E Invoice JSON. sales_invoice must be a Sales Invoice frappe Document (or at least an object with .company/.name)
    """
    einvoice_json = {
        "extend": {},
        "importServicesSeller": {},
        "airlineGoodsDetails": [{}],
        "edcDetails": {},
        "agentEntity": {}
    }

    # pass sales_invoice into functions that need context
    einvoice_json.update(self.get_seller_details_json(sales_invoice))
    einvoice_json.update(self.get_basic_information_json())   # keep existing signature
    einvoice_json.update(self.get_buyer_details_json())       # keep existing signature
    einvoice_json.update(self.get_buyer_extend())
    einvoice_json.update(self.get_good_details())
    einvoice_json.update(self.get_tax_details())
    einvoice_json.update(self.get_summary())
    einvoice_json.update(self.get_payment_details())
    return einvoice_json

def get_seller_details_json(self, sales_invoice):
    efris_log_info(f"[YANA EFRIS] get_seller_details_json() called for {sales_invoice.name}")
    """
    Build sellerDetails section using values on the E Invoice doc (self) first,
    then fall back to values from the Sales Invoice's Company record.
    """
    try:
        # resolve sales_invoice if caller passed a name (defensive)
        if isinstance(sales_invoice, str):
            sales_invoice = frappe.get_doc("Sales Invoice", sales_invoice)

        company_identifier = (
            sales_invoice.custom_branch or sales_invoice.company
        )

        if not company_identifier:
            frappe.throw("No Company or Branch linked to this Sales Invoice. Please select a valid company.")

        # fetch company doc (the branch)
        company = frappe.get_doc("Company", company_identifier)

        # read branch-specific custom fields from Company
        branch_id = getattr(company, "custom_branch_id", "") or ""
        branch_name = getattr(company, "name", "") or "Test"

        seller_email = self.seller_email or getattr(company, "email", None) or getattr(company, "company_email", None)
        if not seller_email:
            # As a last resort, use a dummy fallback to prevent EFRIS rejection
            seller_email = "info@test.com"

        # If branch id missing, log a warning (helps debugging)
        if not branch_id:
            efris_log_info(f"[EFRIS] Warning: Company {company.name} has no branch id configured.")

        seller_details = {
            "sellerDetails": {
                "tin": self.seller_gstin if self.seller_gstin is not None else "",
				"ninBrn": self.seller_nin_or_brn if self.seller_nin_or_brn else "",
				"legalName": self.seller_legal_name if self.seller_legal_name is not None else "",
				"businessName": self.seller_trade_name if self.seller_trade_name is not None else "",
				"mobilePhone": self.seller_phone if self.seller_phone is not None else "",
				"linePhone": "",
				"emailAddress": seller_email,
				"referenceNo": self.seller_reference_no if self.seller_reference_no is not None else "",
                "isCheckReferenceNo": "0",

                # EFRIS branch specifics
                "branchId": branch_id,
                "branchName": branch_name,
                "branchCode": ""
            }
        }

        return seller_details

    except Exception as e:
        frappe.log_error(f"Error getting seller details JSON: {e}", "E Invoice - get_seller_details_json")
        raise

def yana_before_submit(self):
    """Custom override for Uganda Compliance E-Invoice before_submit()"""
    efris_log_info(f"[YANA] Running before_submit for E-Invoice {self.name}")

    try:
        # Fetch related Sales Invoice (the one linked to this E-Invoice)
        sales_invoice = frappe.get_doc('Sales Invoice', self.name)

        # Handle Credit Note (Return) correctly
        if sales_invoice.is_return and sales_invoice.return_against:
            efris_log_info(f"[YANA] Detected Credit Note. Return Against: {sales_invoice.return_against}")
            original_invoice = frappe.get_doc('Sales Invoice', sales_invoice.return_against)
            original_e_invoice = frappe.get_doc('E Invoice',sales_invoice.return_against)
        else:
            efris_log_info("[YANA] Normal Sales Invoice detected.")
            original_invoice = sales_invoice

        # Log IRN/FDN info
        efris_log_info(f"[YANA] Original Invoice: {original_invoice.name}, IRN: {original_invoice.efris_irn}")

        # ✅ Pull IRN/FDN from the original invoice
        fdn = original_invoice.efris_irn
        if fdn:
            self.irn = fdn
            self.original_fdn = original_invoice.efris_irn
            self.invoice_id = original_e_invoice.invoice_id
            self.antifake_code = original_e_invoice.antifake_code
        else:
            msg = _("Cannot submit e-invoice without EFRIS.") + " "
            msg += _("You must generate EFRIS for the sales invoice to submit this e-invoice.")
            efris_log_error(f"[YANA] Missing IRN for original invoice: {original_invoice.name}")
            frappe.throw(msg, title=_("Missing EFRIS"))

    except Exception as e:
        efris_log_error(f"[YANA] Exception in before_submit: {str(e)}")
        frappe.throw(f"Error in YANA before_submit: {e}")
