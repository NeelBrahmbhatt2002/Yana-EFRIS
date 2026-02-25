import frappe
from frappe import _
from frappe.utils import today
from uganda_compliance.efris.api_classes.e_invoice import EInvoiceAPI
from uganda_compliance.efris.api_classes.efris_api import make_post
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error

import json, base64, gzip
from Crypto.Cipher import AES
import frappe
from uganda_compliance.efris.doctype.e_invoice_request_log.e_invoice_request_log import log_request_to_efris
from frappe.utils import cint
from erpnext.selling.page.point_of_sale.point_of_sale import (
    search_by_term,
    filter_result_items,
    get_conditions,
    get_item_group_condition,
    get_stock_availability,
)
from frappe.utils.nestedset import get_root_of
from erpnext.stock.get_item_details import get_conversion_factor


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
    """
    efris_log_info("generate_irn called ...")

    from yana_efris.utils.custom_naming import generate_document_series

    # Ensure doc exists
    sales_invoice = EInvoiceAPI.parse_sales_invoice(sales_invoice)
    original_name = sales_invoice.name
    efris_log_info(f"Parsed invoice: {original_name}")

    # ---------------------------------------------------------------
    # Predict SAL reference ONLY for auto-named invoices
    # ---------------------------------------------------------------
    if sales_invoice.custom_document_name:
        # Manual invoice → do NOT generate SAL
        predicted_sal_reference = sales_invoice.name
        efris_log_info(
            f"[YANA DEBUG] Manual invoice detected. Using existing name as referenceNo: {predicted_sal_reference}"
        )
    else:
        # Auto-named invoice → predict SAL
        _temp_doc = frappe.copy_doc(sales_invoice)
        generate_document_series(_temp_doc, "efris")
        predicted_sal_reference = _temp_doc.name
        efris_log_info(
            f"[YANA DEBUG] Auto invoice. Predicted SAL referenceNo: {predicted_sal_reference}"
        )


    # ---------------------------------------------------------------
    # 1️⃣ Submit to EFRIS FIRST — do NOT rename yet!
    # ---------------------------------------------------------------
    einvoice = EInvoiceAPI.create_einvoice(sales_invoice.name)
    einvoice.fetch_invoice_details()

    einvoice_json = einvoice.get_einvoice_json(sales_invoice)

    try:
        einvoice_json["sellerDetails"]["referenceNo"] = predicted_sal_reference
        efris_log_info(f"[YANA DEBUG] Updated referenceNo in payload: {predicted_sal_reference}")
    except Exception as e:
        efris_log_info(f"[YANA ERROR] Failed to override referenceNo: {e}")

    company_name = sales_invoice.company
    efris_log_info(f"[YANA DEBUG] taxDetails JSON: {frappe.as_json(einvoice_json.get('taxDetails'))}")
    efris_log_info(f"[YANA DEBUG] goodsDetails JSON: {frappe.as_json(einvoice_json.get('goodsDetails'))}")
    efris_log_info(f"[YANA DEBUG] summary JSON: {frappe.as_json(einvoice_json.get('summary'))}")

    status, response = make_post(
        interfaceCode="T109",
        content=einvoice_json,
        company_name=company_name,
        reference_doc_type=sales_invoice.doctype,
        reference_document=sales_invoice.name
    )

    # ---------------------------------------------------------------
    # 2️⃣ If API FAILED → do NOT rename, do NOT set efris_invoice=1
    # ---------------------------------------------------------------
    if not status:
        frappe.throw(response, title=_('EFRIS Generation Failed'))

    # ---------------------------------------------------------------
    # 3️⃣ API SUCCESS → Now rename invoice from PFI → SAL series
    # ---------------------------------------------------------------
    try:
        efris_log_info("EFRIS success, converting invoice to SAL series...")

        # Reload latest version
        sales_invoice = frappe.get_doc("Sales Invoice", original_name)

        # Mark as EFRIS invoice
        sales_invoice.efris_invoice = 1

        # Generate new SAL name
        
        # ---------------------------------------------------------------
        # Rename ONLY auto-named invoices
        # ---------------------------------------------------------------
        if not sales_invoice.custom_document_name:
            generate_document_series(sales_invoice, "efris")
            new_name = sales_invoice.name
        else:
            new_name = original_name

        # Rename in DB
        if original_name != new_name:
            frappe.rename_doc("Sales Invoice", original_name, new_name, force=True)
            efris_log_info(f"Renamed invoice: {original_name} → {new_name}")

            # 🔥 Update EInvoice reference_doc AFTER renaming
            try:
                frappe.rename_doc("E Invoice", einvoice.name, new_name, force=True)
                efris_log_info(f"Renamed EInvoice: {einvoice.name} → {new_name}")
                einvoice = frappe.get_doc("E Invoice", new_name)
                # einvoice.reference_document = new_name
                einvoice.save()
                efris_log_info(f"Updated EInvoice reference_document to {new_name}")
            except Exception as e:
                efris_log_info(f"Failed to update EInvoice reference_document: {e}")

        # Save renamed doc
        sales_invoice = frappe.get_doc("Sales Invoice", new_name)
        sales_invoice.flags.ignore_validate_update_after_submit = True
        sales_invoice.flags.ignore_validate = True
        sales_invoice.flags.ignore_on_update = True
        sales_invoice.flags.ignore_mandatory = True
        sales_invoice.posting_date = frappe.utils.today()
        sales_invoice.posting_time = frappe.utils.nowtime()
        if sales_invoice.due_date == sales_invoice.get_db_value("posting_date"):
            sales_invoice.due_date = frappe.utils.today()
        sales_invoice.save()

    except Exception as e:
        efris_log_info(f"Error renaming invoice after EFRIS success: {e}")
        frappe.throw(f"Invoice renaming failed: {e}")

    # ---------------------------------------------------------------
    # 4️⃣ Continue success workflow
    # ---------------------------------------------------------------
    EInvoiceAPI.handle_successful_irn_generation(einvoice, response)
    efris_log_info(f"EFRIS Generated Successfully. :{einvoice.name}")
    frappe.msgprint(_("EFRIS Generated Successfully."), alert=1)

    return status, response

@staticmethod
def decrypt_aes_ecb(aeskey, ciphertext):

    try:
        # Step 1: Base64 decode
        raw = base64.b64decode(ciphertext)

        data = raw

        # Step 2: If starts with gzip header, decompress
        if data.startswith(b'\x1f\x8b'):
            try:
                data = gzip.decompress(data)
            except Exception as e:
                frappe.log_error(f"❌ GZIP1 failed: {e}", "DEBUG")
                return None

        # Step 3: Try to parse JSON directly
        try:
            text = data.decode("utf-8")
            json.loads(text)  # validate
            return text
        except:
            frappe.log_error("ℹ Not valid JSON yet. Trying AES decrypt...", "DEBUG")

        # Step 4: AES decrypt (ECB, PKCS7)
        cipher = AES.new(aeskey, AES.MODE_ECB)
        decrypted = cipher.decrypt(data)

        padding_length = decrypted[-1]
        decrypted = decrypted[:-padding_length]

        # Step 5: If result is gzip again, decompress
        if decrypted.startswith(b'\x1f\x8b'):
            try:
                decrypted = gzip.decompress(decrypted)
            except Exception as e:
                frappe.log_error(f"❌ GZIP2 failed: {e}", "DEBUG")

        # Step 6: Now decode text
        final_text = decrypted.decode("utf-8")
        return final_text

    except Exception as e:
        frappe.log_error(f"❌ FINAL decrypt error: {e}", "DEBUG")
        raise

@frappe.whitelist()
def query_customer_details(doc, e_company_name, tax_id, ninBrn,accountManager):
    # 1️⃣ Call EFRIS API
    query_customer_details_T119 = {
        "tin": tax_id,
        "ninBrn": ninBrn
    }

    success, response = make_post(
        interfaceCode="T119",
        content=query_customer_details_T119,
        company_name=e_company_name,
    )

    if not success:
        frappe.throw(f"Failed to fetch customer details from EFRIS. Response: {response}")

    # 2️⃣ Extract taxpayer info
    taxpayer = response.get("taxpayer")
    if not taxpayer:
        frappe.throw("EFRIS did not return taxpayer information.")

    # 3️⃣ Choose customer name
    customer_name = taxpayer.get("legalName") or taxpayer.get("businessName")
    if not customer_name:
        frappe.throw("No valid legal/business name found in EFRIS response.")

    # 4️⃣ Optional: double-check if already exists by tax_id
    existing = frappe.db.get_value("Customer", {"tax_id": taxpayer.get("tin")}, "name")
    if existing:
        return {
            "customer_name": existing,
            "message": "Existing customer returned."
        }

    # 5️⃣ Create new Customer
    customer = frappe.new_doc("Customer")
    customer.customer_name = customer_name
    customer.customer_type = "Company"
    customer.efris_customer_type = "B2B"  # ✅ Custom field (make sure it exists)
    customer.account_manager = accountManager
    customer.customer_group = "Commercial"

    # 6️⃣ Map optional fields
    if taxpayer.get("tin"):
        customer.tax_id = taxpayer.get("tin")

    if taxpayer.get("address"):
        # NOTE: Customer doctype normally doesn't have primary_address field by default.
        # If you created a custom field, it's fine.
        customer.primary_address = taxpayer.get("address")

    customer.insert(ignore_permissions=True)   # <--- NO contact created here (email/mobile empty)
    frappe.db.commit()

    if taxpayer.get("contactEmail"):
        customer.db_set("email_id", taxpayer.get("contactEmail"))

    if taxpayer.get("contactNumber"):
        customer.db_set("mobile_no", taxpayer.get("contactNumber"))

    # 7️⃣ Save
    # customer.save()
    # frappe.db.commit()

    return {
        "customer_id": customer.name,
        "customer_name": customer.customer_name,
        "message": "New customer created successfully.",
        "taxpayer": taxpayer,
    }


@frappe.whitelist()
def fetch_items_from_efris(pageNo,pageSize,company_name):
    fetch_items_T127 = {
        "pageNo": pageNo,
        "pageSize": pageSize,
    }

    success, response = make_post(
        interfaceCode="T127",
        content=fetch_items_T127,
        company_name=company_name,
    )

    if not success:
        frappe.throw("Failed to fetch items from EFRIS (T127). Check logs and credentials.")
    
    return response

@frappe.whitelist()
def fetch_live_stock_by_goods_code(goods_code, company=None):
    """
    Fetch item details & live stock from EFRIS using Interface Code T127.
    Stores EFRIS Item ID in Item master for future use.
    """
    if not goods_code:
        return {"success": False, "message": "Missing goods code."}

    payload = {
        "goodsCode": goods_code,
        "pageNo": "1",
        "pageSize": "10"
    }

    success, response = make_post(
        interfaceCode="T127",
        content=payload,
        company_name=company or frappe.defaults.get_user_default("Company")
    )

    if not success:
        return {"success": False, "message": response}

    # Expecting response.records[0]
    record = None
    if isinstance(response, dict) and response.get("records"):
        record = response["records"][0]
    elif isinstance(response, list) and len(response) > 0:
        record = response[0]

    if not record:
        return {"success": False, "message": "No item found in EFRIS."}

    item_id = record.get("id")
    stock = record.get("stock")

    return {"success": True, "live_stock": stock, "efris_item_id": item_id}

@frappe.whitelist()
def validate_fdn_number(fdn_number, company=None):
    """
    Validate Invoice FDN Number using EFRIS Interface Code T108.
    Returns RAW EFRIS response (no custom formatting).
    """

    if not fdn_number:
        return {"error": "FDN Number is required."}

    payload = {
        "invoiceNo": fdn_number
    }

    # Call using same pattern as other functions
    success, response = make_post(
        interfaceCode="T108",
        content=payload,
        company_name=company or frappe.defaults.get_user_default("Company")
    )

    if not success:
        return {"success": False, "message": response}
    
    goods = response.get("goodsDetails", [])
    seller = response.get("sellerDetails", {})
    basic = response.get("basicInformation", {})
    tax_details = response.get("taxDetails", [])
    summary = response.get("summary", {})

    # 2. Check if all items exist in ERPNext
    missing_items = []
    for g in goods:
        item_code = g.get("itemCode")
        if not frappe.db.exists("Item", item_code):
            missing_items.append(item_code)

    if missing_items:
        frappe.throw(f"Items not found in ERPNext: {', '.join(missing_items)}")

    # Return raw EFRIS response exactly as received
    return {
        "seller": seller,
        "basic": basic,
        "goods": goods,
        "tax_details": tax_details,
        "summary": summary
    }


def get_efris_product_code(item_code):
	product_code = frappe.db.get_value("Item", item_code, "item_code")
	if not product_code:
		frappe.throw(f"No EFRIS Product Code found for item: {item_code}")
	return product_code

@frappe.whitelist()
def get_sidebar_items():
    user_roles = set(frappe.get_roles(frappe.session.user))  # Use a set for faster lookups
    
    # Prepare sidebar items for user role "System Manager"
    def get_system_manager_items():
        return [
            {
                "categoryName": _("System Management"), "link": "", "icon": "setting-gear", "items": [
                    {"label": _("Workflows"), "link": f"/app/workflow", "icon": "workflow", "items": []},
                    {"label": _("Notifications"), "link": f"/app/notification", "icon": "notification", "items": []},
                    {"label": _("Client Scripts"), "link": f"/app/client-script", "icon": "small-file", "items": []},
                    {"label": _("Property Settings"), "link": f"/app/property-setter", "icon": "shortcut", "items": []},
                    {"label": _("System Settings"), "link": f"/app/system-settings", "icon": "tool", "items": []},
                    {"label": _("Role Permissions Management"), "link": f"/app/permission-manager", "icon": "permission", "items": []},
                ]
            },
            {
                "categoryName": _("Logs"), "link": "", "icon": "list-alt", "items": [
                    {"label": _("Activity Logs"), "link": f"/app/activity-log", "icon": "list-alt", "items": []},
                    {"label": _("View Logs"), "link": f"/app/view-log", "icon": "list-alt", "items": []},
                    {"label": _("Access Logs"), "link": f"/app/access-log", "icon": "list-alt", "items": []},
                    {"label": _("Error Logs"), "link": f"/app/error-log", "icon": "list-alt", "items": []},
                ]
            },
        ]
        
    # Map roles to function references directly
    sidebar_items = {
        "System Manager": get_system_manager_items,
    }
    
    # If the user has the role "System Manager", return the items for that role
    if "System Manager" in user_roles:
        return {"System Manager": sidebar_items["System Manager"]()}
        
    # Find the first matching role (assuming each user has only one role)
    for role in user_roles:
        if role in sidebar_items:
            function = sidebar_items[role]  # Get the function reference
            return {role: function()}  # Call the function directly

    return {}  # Return empty if no matching role is found


@frappe.whitelist()
def get_items(start, page_length, item_group, pos_profile, search_term=""):

    frappe.log_error(f"Custom POS items started working", "Custom POS Items Filter")
    # Get POS Profile data
    # warehouse, hide_unavailable_items, company = frappe.db.get_value(
    #     "POS Profile",
    #     pos_profile,
    #     ["warehouse", "hide_unavailable_items", "company"],
    # )

    warehouse, hide_unavailable_items, company, price_list = frappe.db.get_value(
        "POS Profile",
        pos_profile,
        ["warehouse", "hide_unavailable_items", "company", "selling_price_list"],
    )


    if not warehouse:
        frappe.throw("Warehouse is not set in POS Profile.")

    result = []

    # 🔎 Search handling
    if search_term:
        result = search_by_term(search_term, warehouse, price_list) or []
        filter_result_items(result, pos_profile)
        if result:
            return {"items": result}

    if not frappe.db.exists("Item Group", item_group):
        item_group = get_root_of("Item Group")

    condition = get_conditions(search_term)
    condition += get_item_group_condition(pos_profile)

    lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])

    # 🔥 FORCE warehouse-based filtering ALWAYS (KEY FIX)
    bin_join_selection = """
        INNER JOIN `tabBin` bin
            ON bin.item_code = item.name
            AND bin.warehouse = %(warehouse)s
    """

    bin_join_condition = ""

    items_data = frappe.db.sql(
        f"""
        SELECT
            item.name AS item_code,
            item.item_name,
            item.description,
            item.stock_uom,
            item.image AS item_image,
            item.is_stock_item,
            item.sales_uom
        FROM
            `tabItem` item
            {bin_join_selection}
        WHERE
            item.disabled = 0
            AND item.has_variants = 0
            AND item.is_sales_item = 1
            AND item.is_fixed_asset = 0
            AND item.item_group IN (
                SELECT name FROM `tabItem Group`
                WHERE lft >= {cint(lft)} AND rgt <= {cint(rgt)}
            )
            AND {condition}
        ORDER BY
            item.name ASC
        LIMIT
            {cint(page_length)} OFFSET {cint(start)}
        """,
        {"warehouse": warehouse},
        as_dict=1,
    )

    if not items_data:
        return {"items": []}

    current_date = frappe.utils.today()

    for item in items_data:

        # item.actual_qty, _ = get_stock_availability(item.item_code, warehouse)
        item.actual_qty, _, is_negative_stock_allowed = get_stock_availability(
            item.item_code, warehouse
        )


        item_prices = frappe.get_all(
            "Item Price",
            fields=[
                "price_list_rate",
                "currency",
                "uom",
                "batch_no",
                "valid_from",
                "valid_upto",
            ],
            filters={
                "price_list": price_list,
                "item_code": item.item_code,
                "selling": True,
                "valid_from": ["<=", current_date],
                "valid_upto": ["in", [None, "", current_date]],
            },
            order_by="valid_from desc",
        )

        stock_uom_price = next(
            (d for d in item_prices if d.get("uom") == item.stock_uom), {}
        )

        item_uom = item.stock_uom
        item_uom_price = stock_uom_price

        if item.sales_uom and item.sales_uom != item.stock_uom:
            item_uom = item.sales_uom
            sales_uom_price = next(
                (d for d in item_prices if d.get("uom") == item.sales_uom), {}
            )
            if sales_uom_price:
                item_uom_price = sales_uom_price

        if item_prices and not item_uom_price:
            item_uom = item_prices[0].get("uom")
            item_uom_price = item_prices[0]

        item_conversion_factor = get_conversion_factor(
            item.item_code, item_uom
        ).get("conversion_factor")

        if item.stock_uom != item_uom:
            item.actual_qty = item.actual_qty // item_conversion_factor

        if item_uom_price and item_uom != item_uom_price.get("uom"):
            item_uom_price.price_list_rate = (
                item_uom_price.price_list_rate * item_conversion_factor
            )

        result.append(
            {
                **item,
                "price_list_rate": item_uom_price.get("price_list_rate"),
                "currency": item_uom_price.get("currency"),
                "uom": item_uom,
                "batch_no": item_uom_price.get("batch_no"),
            }
        )

    return {"items": result}

@frappe.whitelist()
def get_files_in_folder(folder: str, start: int = 0, page_length: int = 20) -> dict:

    current_user = frappe.session.user

    # Get attachment folder (only if belongs to user)
    attachment_folder = frappe.db.get_value(
        "File",
        {
            "file_url": "Home/Attachments",
            "owner": current_user
        },
        ["name", "file_name", "file_url", "is_folder", "modified"],
        as_dict=1,
    )

    # Only fetch files owned by logged-in user
    files = frappe.get_list(
        "File",
        {
            "folder": folder,
            "owner": current_user
        },
        ["name", "file_name", "file_url", "is_folder", "modified"],
        start=start,
        page_length=page_length + 1,
    )

    # Insert user’s attachment folder if needed
    if folder == "Home" and attachment_folder and attachment_folder not in files:
        files.insert(0, attachment_folder)

    return {
        "files": files[:page_length],
        "has_more": len(files) > page_length
    }