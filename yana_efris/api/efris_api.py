import frappe
from frappe import _
from frappe.utils import today
from uganda_compliance.efris.api_classes.e_invoice import EInvoiceAPI
from uganda_compliance.efris.api_classes.efris_api import make_post
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error

@frappe.whitelist()
def get_exchange_rate(currency=None, company_name=None):
    """
    Fetch exchange rate for a currency.
    1. Return 1.0 if same as company currency.
    2. Check Currency Exchange for today's rate (cache-first).
    3. If not found, call EFRIS, insert/update, and return.
    """
    try:
        from uganda_compliance.efris.api_classes.efris_api import make_post

        # Get company's base currency
        company_currency = frappe.db.get_value("Company", company_name, "default_currency")

        # 🛑 If same currency → no conversion needed
        if company_currency == currency:
            return {"currency": currency, "rate": 1.0}

        # 🔍 Step 1: Check ERPNext Currency Exchange for today's rate
        existing_rate = frappe.db.get_value(
            "Currency Exchange",
            {
                "from_currency": currency,
                "to_currency": company_currency,
                "date": today()
            },
            "exchange_rate"
        )

        if existing_rate:
            return {"currency": currency, "rate": float(existing_rate)}

        # 🌍 Step 2: If not found → call EFRIS
        interfaceCode = "T121"
        content = {
            "currency": currency,
        }

        success, response = make_post(
            interfaceCode=interfaceCode,
            content=content,
            company_name=company_name
        )

        if not success:
            frappe.log_error(response, "EFRIS Exchange Rate Fetch Failed")
            frappe.throw(response)

        rate = float(response.get("rate") or 0)
        if not rate:
            frappe.throw("No exchange rate returned from EFRIS")

        # Save into Currency Exchange
        exchange = frappe.get_doc({
            "doctype": "Currency Exchange",
            "from_currency": currency,
            "to_currency": company_currency,
            "exchange_rate": rate,
            "date": today()
        })
        exchange.insert(ignore_permissions=True, ignore_mandatory=True)
        frappe.db.commit()


        # return {"currency": currency, "rate": rate}
        return response

    except Exception as e:
        frappe.log_error(f"EFRIS exchange rate error: {e}", "yana_efris.get_exchange_rate")
        # frappe.throw(f"EFRIS exchange rate call failed: {e}")

@frappe.whitelist()
def fetch_efris_branches(company_name=None):
    """
    Simple flow:
      - call EFRIS T138 (make_post)
      - for each returned branch, find Company with exact matching company_name or name
        (case-insensitive, trimmed)
      - set Company.custom_branch_id = branchId via db_set
    Returns: { success: True, mapped: [...], not_found: [...] } or error
    """
    try:
        # import your make_post helper (adjust path as needed)
        from uganda_compliance.efris.api_classes.efris_api import make_post

        status, response = make_post(interfaceCode="T138", content=None, company_name=company_name)
        if not status:
            frappe.log_error(f"EFRIS T138 failed: {response}", "Yana EFRIS - fetch_efris_branches_and_map")
            return {"success": False, "error": response}

        # normalize response -> list of branch dicts
        if isinstance(response, list):
            items = response
        elif isinstance(response, dict):
            items = response.get("branches") or response.get("data") or []
        else:
            items = []

        mapped = []
        not_found = []

        for b in items:
            branch_id = b.get("branchId") or b.get("branch_id") or ""
            branch_name = (b.get("branchName") or b.get("branch_name") or "").strip()

            if not branch_name:
                # skip nameless entries
                continue

            # Exact match search (case-insensitive). First try company_name, then name.
            # Using filters with "=" does case-sensitive matching in DB, so perform normalized compare in Python.
            # Fetch candidate companies and compare normalized strings to simulate case-insensitive exact match.
            candidates = frappe.get_all("Company", fields=["name", "company_name"])
            matched_company = None
            lower_branch = branch_name.lower()

            for c in candidates:
                comp_name = (c.get("company_name") or c.get("name") or "").strip()
                comp_key_name = (c.get("name") or "").strip()
                if comp_name and comp_name.lower() == lower_branch:
                    matched_company = c["name"]
                    break
                if comp_key_name and comp_key_name.lower() == lower_branch:
                    matched_company = c["name"]
                    break

            if matched_company:
                # update Company.custom_branch_id if column exists
                if frappe.db.has_column("Company", "custom_branch_id"):
                    try:
                        frappe.get_doc("Company", matched_company).db_set("custom_branch_id", branch_id)
                    except Exception as e:
                        frappe.log_error(f"Failed to db_set custom_branch_id for {matched_company}: {e}",
                                         "Yana EFRIS - fetch_efris_branches_and_map")
                else:
                    frappe.log_error("Company table missing 'custom_branch_id' column", "Yana EFRIS - fetch_efris_branches_and_map")

                mapped.append({"company": matched_company, "branchName": branch_name, "branchId": branch_id})
            else:
                not_found.append({"branchName": branch_name, "branchId": branch_id})

        return {"success": True, "mapped": mapped, "not_found": not_found}

    except Exception as e:
        frappe.log_error(f"Exception in fetch_efris_branches_and_map: {e}", "Yana EFRIS - fetch_efris_branches_and_map")
        return {"success": False, "error": str(e)}

@staticmethod
def generate_irn(sales_invoice):
    """
    Entry point (server-side) that builds the EFRIS payload and submits it.
    sales_invoice may be a name or a dict/doc - parse_sales_invoice should return a frappe Document.
    """
    efris_log_info("generate_irn called ...")

    # Ensure we have a Sales Invoice Doc (frappe Document) - parse_sales_invoice should return a doc
    sales_invoice = EInvoiceAPI.parse_sales_invoice(sales_invoice)
    efris_log_info(f"after parse done... Sales Invoice: {sales_invoice.name}")

    # Create E Invoice doc (traceability) and fetch any additional details
    einvoice = EInvoiceAPI.create_einvoice(sales_invoice.name)
    einvoice.fetch_invoice_details()

    # Build payload - pass sales_invoice doc into get_einvoice_json so we can read branch/company directly
    einvoice_json = einvoice.get_einvoice_json(sales_invoice)

    # debug log seller part to verify branch fields are present
    try:
        seller_part = einvoice_json.get("sellerDetails") or einvoice_json.get("sellerDetails", {})
        efris_log_info(f"Built sellerDetails for {sales_invoice.name}: {frappe.as_json(seller_part)}")
    except Exception:
        # fallback safe logging
        efris_log_info("Built einvoice_json (sellerDetails logging failed)")

    company_name = sales_invoice.company
    status, response = make_post(
        interfaceCode="T109",
        content=einvoice_json,
        company_name=company_name,
        reference_doc_type=sales_invoice.doctype,
        reference_document=sales_invoice.name
    )

    if status:
        EInvoiceAPI.handle_successful_irn_generation(einvoice, response)
        efris_log_info(f"EFRIS Generated Successfully. :{einvoice.name}")
        frappe.msgprint(_("EFRIS Generated Successfully."), alert=1)
    else:
        # response may be dict or str; keep it readable
        frappe.throw(response, title=_('EFRIS Generation Failed'))

    return status, response
