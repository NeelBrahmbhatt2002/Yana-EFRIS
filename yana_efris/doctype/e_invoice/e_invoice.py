import frappe
from frappe import _
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from frappe.utils import now_datetime
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error
from uganda_compliance.efris.doctype.e_invoice.e_invoice import _get_valid_document

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

def get_tax_details(self):
    efris_log_info("[YANA EFRIS ✅] get_tax_details() called")
    tax_details_list = []

    # Get category-wise tax totals (already Decimal-safe from your override)
    tax_per_category = calculate_tax_by_category(self.invoice)
    trimmed_response = {}

    for key, value in tax_per_category.items():
        # Extract numeric part inside parentheses, e.g., "VAT (18%)" → "18"
        try:
            tax_category = key.split('(')[1].split(')')[0]
            tax_category = tax_category.replace('%', '')
            trimmed_response[tax_category] = Decimal(str(value))
        except Exception:
            continue

    for row in self.taxes:
        try:
            tax_rate_key = '0'
            if str(row.tax_rate) == '0.18':
                tax_rate = Decimal(str(row.tax_rate))
                tax_rate_key = str(int(tax_rate * 100))  # "18"
            else:
                tax_rate_key = str(row.tax_rate)

            tax_category = (row.tax_category_code or '').split(':')[0]

            # ✅ Default to zero if not found in trimmed_response
            calculated_tax = trimmed_response.get(tax_rate_key, Decimal('0.00'))

            # ✅ Use consistent rounding
            calculated_tax = calculated_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            net_amount = Decimal(str(row.net_amount or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            gross_amount = (net_amount + calculated_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            # ✅ Optional: safety correction if mismatch between additional discounts
            additional_disc_total = Decimal(str(calculate_additional_discounts(self.invoice) or 0)).quantize(Decimal('0.01'))
            if calculated_tax > 0 and calculated_tax != additional_disc_total:
                calculated_tax = additional_disc_total
                gross_amount = (net_amount + calculated_tax).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

            tax_details = {
                "taxCategoryCode": tax_category,
                "netAmount": str(net_amount),
                "taxRate": str(row.tax_rate),
                "taxAmount": str(calculated_tax),
                "grossAmount": str(gross_amount),
                "exciseUnit": "",
                "exciseCurrency": "",
                "taxRateName": ""
            }

            tax_details_list.append(tax_details)

        except Exception as e:
            efris_log_info(f"[YANA TAX ERROR] get_tax_details failed for {row.name}: {e}")
            continue

    return {"taxDetails": tax_details_list}


def calculate_tax_by_category(invoice):
    """
    Calculate total tax per tax category for Sales Invoice items.
    Ensures that TaxDetails total matches GoodsDetails tax sum exactly.
    """
    efris_log_info("[YANA EFRIS ✅] calculate_tax_by_category() called")

    doc = _get_valid_document(invoice)

    if not doc.taxes:
        return

    item_taxes = json.loads(doc.taxes[0].item_wise_tax_detail)
    tax_category_totals = defaultdict(Decimal)

    for row in doc.get('items', []):
        item_code = row.get('item_code', '')
        item_tax_template = row.get('item_tax_template', '')
        if not item_tax_template:
            continue

        tax_rate = Decimal(str(item_taxes.get(item_code, [0, 0])[0] or 0))

        # ✅ Use consistent Decimal rounding instead of float
        raw_item_tax = getattr(row, "efris_dsct_item_tax", None)
        if raw_item_tax is None or raw_item_tax == 0:
            # Fallback: recompute from amount and tax rate
            raw_item_tax = Decimal(str(row.amount or 0)) * (tax_rate / (100 + tax_rate))

        item_tax = raw_item_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        # If there’s an additional discount, add its tax portion (with rounding)
        if getattr(doc, "additional_discount_percentage", 0) > 0:
            discount_tax = Decimal(str(getattr(row, "efris_dsct_discount_tax", 0) or 0))
            item_tax += discount_tax.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        tax_category_totals[item_tax_template] += item_tax

    # ✅ Convert Decimal totals to float for downstream compatibility
    return {k: float(v.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) for k, v in tax_category_totals.items()}

# def yana_before_submit(self):
#     """Custom override for Uganda Compliance E-Invoice before_submit()"""
#     efris_log_info(f"[YANA] Running before_submit for E-Invoice {self.name}")

#     try:
#         # Fetch related Sales Invoice (the one linked to this E-Invoice)
#         sales_invoice = frappe.get_doc('Sales Invoice', self.name)

#         # Handle Credit Note (Return) correctly
#         if sales_invoice.is_return and sales_invoice.return_against:
#             efris_log_info(f"[YANA] Detected Credit Note. Return Against: {sales_invoice.return_against}")
#             original_invoice = frappe.get_doc('Sales Invoice', sales_invoice.return_against)
#             original_e_invoice = frappe.get_doc('E Invoice',sales_invoice.return_against)
#         else:
#             efris_log_info("[YANA] Normal Sales Invoice detected.")
#             original_invoice = sales_invoice

#         # Log IRN/FDN info
#         efris_log_info(f"[YANA] Original Invoice: {original_invoice.name}, IRN: {original_invoice.efris_irn}")

#         # ✅ Pull IRN/FDN from the original invoice
#         fdn = original_invoice.efris_irn
#         if fdn:
#             self.irn = fdn
#             self.original_fdn = original_invoice.efris_irn
#             self.invoice_id = original_e_invoice.invoice_id
#             self.antifake_code = original_e_invoice.antifake_code
#         else:
#             msg = _("Cannot submit e-invoice without EFRIS.") + " "
#             msg += _("You must generate EFRIS for the sales invoice to submit this e-invoice.")
#             efris_log_error(f"[YANA] Missing IRN for original invoice: {original_invoice.name}")
#             frappe.throw(msg, title=_("Missing EFRIS"))

#     except Exception as e:
#         efris_log_error(f"[YANA] Exception in before_submit: {str(e)}")
#         frappe.throw(f"Error in YANA before_submit: {e}")
