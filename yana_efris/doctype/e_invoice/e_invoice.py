import frappe
from frappe import _
import json
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from frappe.utils import now_datetime
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error
from uganda_compliance.efris.doctype.e_invoice.e_invoice import _get_valid_document
from uganda_compliance.efris.doctype.e_invoice.e_invoice import _calculate_taxes_and_discounts
from uganda_compliance.efris.doctype.e_invoice.e_invoice import calculate_tax_by_category

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
    efris_log_info("Getting tax details JSON")
    tax_details_list = []

    # 1️⃣ Calculate tax per category
    tax_per_category = calculate_tax_by_category(self.invoice)
    trimmed_response = {}
    for key, value in tax_per_category.items():
        # Extract the part inside the parentheses
        tax_category = key.split('(')[1].split(')')[0]
        tax_category = tax_category.replace('%', '')
        trimmed_response[tax_category] = value

    for row in self.taxes:
        tax_rate_key = '0'
        if row.tax_rate == '0.18':
            tax_rate = float(row.tax_rate)
            tax_rate_key = str(int(tax_rate * 100))  # e.g. 18 for 18%
        else:
            tax_rate_key = row.tax_rate

        tax_category = row.tax_category_code.split(':')[0]

        # 2️⃣ Get calculated tax (from our earlier per-category map)
        calculated_tax = 0.0
        if tax_rate_key in trimmed_response:
            raw_tax = trimmed_response[tax_rate_key]
            calculated_tax = round(float(raw_tax), 2)

            # Debug before rounding adjustment
            efris_log_info(f"[DEBUG] Raw calculated_tax for rate {tax_rate_key}%: {raw_tax} -> Rounded: {calculated_tax}")

        # 3️⃣ Handle mismatches or override conditions
        try:
            expected_discount_tax = calculate_additional_discounts(self.invoice)
            if calculated_tax > 0 and calculated_tax != expected_discount_tax:
                efris_log_info(f"[DEBUG] Adjusting tax for rate {tax_rate_key}% from {calculated_tax} → {expected_discount_tax} (due to discount mismatch)")
                calculated_tax = expected_discount_tax
        except Exception as ex:
            efris_log_info(f"[DEBUG] No discount adjustment applied: {ex}")

        # 4️⃣ Convert to float-safe fixed precision (for JSON safety)
        calculated_tax = float(f"{calculated_tax:.2f}")

        # 5️⃣ Debug summary for final value
        efris_log_info(f"[DEBUG] Final tax for {tax_category} @ {row.tax_rate}: {calculated_tax}")

        gross_amount = round(row.net_amount + calculated_tax, 2)

        efris_log_info(f"[DEBUG] Gross = Net({row.net_amount}) + Tax({calculated_tax}) = {gross_amount}")

        # 6️⃣ Append finalized object
        tax_details = {
            "taxCategoryCode": tax_category,
            "netAmount": f"{row.net_amount:.2f}",
            "taxRate": str(row.tax_rate),
            "taxAmount": f"{calculated_tax:.2f}",
            "grossAmount": f"{gross_amount:.2f}",
            "exciseUnit": "",
            "exciseCurrency": "",
            "taxRateName": ""
        }

        tax_details_list.append(tax_details)

    # 7️⃣ Log final taxDetails summary for cross-check
    total_tax = sum(float(td["taxAmount"]) for td in tax_details_list)
    efris_log_info(f"[DEBUG] ✅ Total Tax from taxDetails = {total_tax:.2f}")

    return {"taxDetails": tax_details_list}


# def calculate_tax_by_category(invoice):
#     """
#     Use same per-item tax numbers that goodsDetails uses so Section D == Section E.
#     Returns: { tax_template_name: Decimal('...') } with values quantized to 2 decimals.
#     """
#     efris_log_info("[YANA EFRIS] calculate_tax_by_category() called (align-with-goods)")

#     doc = _get_valid_document(invoice)
#     if not doc or not getattr(doc, "taxes", None):
#         return {}

#     # load item-wise tax details if present (for rate fallback)
#     try:
#         item_taxes = json.loads(doc.taxes[0].item_wise_tax_detail)
#     except Exception:
#         item_taxes = {}

#     tax_category_totals = defaultdict(Decimal)

#     for row in doc.get("items", []):
#         item_code = row.get("item_code", "")
#         item_tax_template = row.get("item_tax_template", "")
#         if not item_tax_template:
#             continue

#         # determine tax_rate fallback (Decimal)
#         try:
#             raw_rate = item_taxes.get(item_code, [0, 0])[0] or 0
#             tax_rate = Decimal(str(raw_rate))
#         except Exception:
#             tax_rate = Decimal("0")

#         # 1) Prefer explicit efris_dsct_item_tax (discount item tax)
#         raw_item_tax_field = getattr(row, "efris_dsct_item_tax", None)
#         if raw_item_tax_field not in (None, "", 0):
#             item_tax = Decimal(str(raw_item_tax_field))
#             source = "efris_dsct_item_tax"
#         else:
#             # 2) Prefer the stored row.tax (this is what goodsDetails uses)
#             row_tax_field = getattr(row, "tax", None)
#             if row_tax_field not in (None, "", 0):
#                 item_tax = Decimal(str(row_tax_field))
#                 source = "row.tax"
#             else:
#                 # 3) Fallback: recompute from amount using tax-inclusive formula
#                 amount = Decimal(str(getattr(row, "amount", 0) or 0))
#                 if tax_rate == 0:
#                     item_tax = Decimal("0")
#                 else:
#                     item_tax = amount * (tax_rate / (Decimal("100") + tax_rate))
#                 source = "computed"

#         # include discount tax (if present)
#         try:
#             if getattr(doc, "additional_discount_percentage", 0):
#                 discount_tax_val = getattr(row, "efris_dsct_discount_tax", None)
#                 if discount_tax_val not in (None, "", 0):
#                     item_tax += Decimal(str(discount_tax_val))
#         except Exception:
#             pass

#         # Debug: compare goods row.tax and computed value (temporary)
#         efris_log_info(
#             f"[YANA COMPARE ROW] item={item_code}, template={item_tax_template}, "
#             f"source={source}, item_tax_used={item_tax}, row.tax={getattr(row,'tax',None)}, "
#             f"efris_dsct_item_tax={getattr(row,'efris_dsct_item_tax',None)}, "
#             f"efris_dsct_discount_tax={getattr(row,'efris_dsct_discount_tax',None)}"
#         )

#         tax_category_totals[item_tax_template] += Decimal(item_tax)

#     # Round once per category (single rounding)
#     final_totals = {}
#     for k, v in tax_category_totals.items():
#         final_totals[k] = v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

#     efris_log_info(f"[YANA CATEGORY TOTALS] { {k: str(v) for k,v in final_totals.items()} }")
#     return final_totals


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
