import frappe
from frappe.utils import cint, now_datetime
import math

# ─────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────
PAGE_SIZE = 99          # EFRIS max page size -> fewer API calls
MAX_ITEMS_PER_CLICK = 50  # per user click

# ─────────────────────────────────────────────────────
# Public entrypoint from button
# ─────────────────────────────────────────────────────
@frappe.whitelist()
def enqueue_sync_efris_items(company_name: str):
    frappe.log_error(f"Enqueue requested for company={company_name}", "Page Skip Debug")
    frappe.enqueue(
        method="yana_efris.api.efris_item_sync.sync_efris_items",
        queue="long",
        job_name=f"EFRIS Item Sync ({company_name})",
        company_name=company_name,
    )
    return "Sync started in background."

# ─────────────────────────────────────────────────────
# Progress helpers
# ─────────────────────────────────────────────────────
def get_or_create_progress(company_name: str):
    """Create or fetch progress row. Auto-initialize if company already has items."""
    name = frappe.db.get_value("EFRIS Sync Progress", {"company": company_name})
    if name:
        frappe.log_error(f"Progress row found name={name} for company={company_name}", "Page Skip Debug")
        return frappe.get_doc("EFRIS Sync Progress", name)

    # 🧮 auto-initialize based on existing Item records
    existing_items = frappe.db.count("Item", {"efris_e_company": company_name})
    if existing_items:
        page_no = math.floor(existing_items / PAGE_SIZE) + 1
        offset = existing_items % PAGE_SIZE
        frappe.log_error(
            f"Initializing sync progress for {company_name} with existing {existing_items} items -> page={page_no}, offset={offset}",
            "Page Skip Debug",
        )
    else:
        page_no, offset = 1, 0
        frappe.log_error(f"No existing items for {company_name}. start page=1 offset=0", "Page Skip Debug")

    doc = frappe.new_doc("EFRIS Sync Progress")
    doc.company = company_name
    doc.last_synced_page = page_no
    doc.last_synced_offset = offset
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.log_error(f"Progress row created name={doc.name} page={page_no} offset={offset}", "Page Skip Debug")
    return doc

def get_tax_template_for_company(company_name: str, rec: dict):
    """Choose correct Item Tax Template based on EFRIS item details."""
    rate_raw = (rec.get("taxRate") or "").strip()
    title_hint = None

    # Convert to float safely
    try:
        rate_float = float(rate_raw)
    except Exception:
        rate_float = None

    # Normalize rate → detect type
    if rate_float is not None:
        if abs(rate_float - 0.18) < 0.0001:
            title_hint = "Standard"
        elif abs(rate_float - 0.00) < 0.0001:
            title_hint = "Zero"
        elif abs(rate_float) < 0.0001:
            title_hint = "Exempt"
    elif rate_raw in ["-", "EXEMPT", "Exempt"]:
        title_hint = "Exempt"
    elif "deemed" in (rec.get("goodsName") or "").lower():
        title_hint = "Deemed"

    filters = {"company": company_name}
    if title_hint:
        filters["title"] = ["like", f"%{title_hint}%"]

    template = frappe.db.get_value("Item Tax Template", filters, "name")

    if not template:
        frappe.log_error(
            f"No matching tax template for company={company_name}, rate={rate_raw}, title_hint={title_hint}",
            "EFRIS TAX TEMPLATE MISSING"
        )
    else:
        frappe.log_error(f"Template found: {template} for rate={rate_raw}", "Page Skip Debug")

    return template

def update_progress(progress_doc, page_no: int, offset: int):
    """Persist progress (page + offset)."""
    old_page = progress_doc.last_synced_page
    old_offset = progress_doc.last_synced_offset
    progress_doc.last_synced_page = cint(page_no)
    progress_doc.last_synced_offset = cint(offset)
    progress_doc.save(ignore_permissions=True)
    frappe.db.commit()
    frappe.log_error(
        f"Progress updated for company={progress_doc.company}: {old_page}/{old_offset} -> {page_no}/{offset}",
        "Page Skip Debug",
    )

# ─────────────────────────────────────────────────────
# Main sync job (incremental, per-company, paginated)
# ─────────────────────────────────────────────────────
def sync_efris_items(company_name: str):
    created_count = 0

    progress = get_or_create_progress(company_name)
    page_no = max(1, cint(progress.last_synced_page) or 1)
    offset = max(0, cint(progress.last_synced_offset) or 0)

    frappe.log_error(f"SYNC START company={company_name} start_page={page_no} start_offset={offset}", "Page Skip Debug")

    while created_count < MAX_ITEMS_PER_CLICK:
        frappe.log_error(f"Fetching page {page_no} (page_size={PAGE_SIZE}) offset={offset} created_count={created_count}", "Page Skip Debug")
        records, page_info = fetch_efris_items_page(company_name, page_no, PAGE_SIZE)

        # After fetch: log sizes and page_info
        try:
            page_count_val = int(page_info.get("pageCount") or 0)
        except Exception:
            page_count_val = 0
        frappe.log_error(f"After fetch: page={page_no} got_records={len(records)} page_info={page_info}", "Page Skip Debug")

        # If nothing returned, we are likely past end
        if not records:
            frappe.log_error(f"No records on page {page_no}. Marking complete. page_info={page_info}", "Page Skip Debug")
            # show final msg once (server-side)
            try:
                frappe.msgprint({
                    "title": __("EFRIS Sync Complete"),
                    "indicator": "green",
                    "message": __(f"✅ All EFRIS items have been synced successfully for {company_name}.")
                })
            except Exception:
                # msgprint may be ignored in async, but log anyway
                frappe.log_error("msgprint failed (likely background job).", "Page Skip Debug")

            # Mark as complete: set to next page, offset 0
            update_progress(progress, page_no + 1, 0)
            break

        # Guard offset (in case the page is shorter than expected)
        if offset >= len(records):
            frappe.log_error(
                f"OFFSET >= len(records) -> offset={offset} len(records)={len(records)} on page={page_no}. "
                f"Will move to next page.",
                "Page Skip Debug"
            )
            # move to next page
            page_no += 1
            offset = 0
            update_progress(progress, page_no, offset)

            # Check if we’re past total pages (if provided)
            if page_count_val and page_no > page_count_val:
                frappe.log_error(
                    f"Offset guard moved past page_count -> page_no={page_no} page_count={page_count_val}. Ending.",
                    "Page Skip Debug"
                )
                break
            # continue to fetch next page
            continue

        # Process from current offset
        i = offset
        # log entry to mark processing start of page slice
        frappe.log_error(f"Processing records from index {offset} on page {page_no}.", "Page Skip Debug")

        while i < len(records) and created_count < MAX_ITEMS_PER_CLICK:
            rec = records[i]
            code = (rec.get("goodsCode") or "").strip()

            # Log the record we're about to inspect
            frappe.log_error(f"Inspecting record page={page_no} index={i} code={code}", "Page Skip Debug")

            if not code:
                frappe.log_error(f"Skipping record with empty code page={page_no} index={i}", "Page Skip Debug")
                i += 1
                continue

            # If exists, skip but log (so you can see many existing items causing fast page progression)
            if frappe.db.exists("Item", code):
                frappe.log_error(f"Skipping existing Item code={code} page={page_no} index={i}", "Page Skip Debug")
            else:
                try:
                    created = create_simple_item(rec, company_name)
                    if created:
                        created_count += 1
                        frappe.log_error(
                            f"ITEM CREATED code={code} page={page_no} index={i} total_created={created_count}",
                            "Page Skip Debug"
                        )
                    else:
                        frappe.log_error(f"create_simple_item returned False for code={code} page={page_no} index={i}", "Page Skip Debug")
                except Exception:
                    tb = frappe.get_traceback()
                    frappe.log_error(f"Exception while creating Item code={code} page={page_no} index={i} trace={tb}", "Page Skip Debug")

            i += 1

        # If we hit the per-click limit and stopped mid-page
        if created_count >= MAX_ITEMS_PER_CLICK:
            new_offset = i if i <= len(records) else 0
            frappe.log_error(f"Reached MAX_ITEMS_PER_CLICK={MAX_ITEMS_PER_CLICK}. Saving page={page_no} offset={new_offset}", "Page Skip Debug")
            update_progress(progress, page_no, new_offset)
            break

        # finished processing whole page; move to next page
        old_page = page_no
        page_no += 1
        offset = 0
        frappe.log_error(f"Finished page {old_page}. Moving to next page {page_no}.", "Page Skip Debug")
        update_progress(progress, page_no, offset)

        # Optional: if page_count present and we've passed it, break
        if page_count_val and page_no > page_count_val:
            frappe.log_error(f"page_no {page_no} > page_count {page_count_val}. Ending.", "Page Skip Debug")
            break

    frappe.log_error(
        f"Sync run finished for company={company_name}. Created this run: {created_count}. Next start => page {page_no}, offset {offset}",
        "EFRIS SYNC SUMMARY"
    )

# ─────────────────────────────────────────────────────
# Fetch one page from EFRIS
# ─────────────────────────────────────────────────────
def fetch_efris_items_page(company_name: str, page_no: int, page_size: int):
    from uganda_compliance.efris.api_classes.efris_api import make_post

    payload = {"pageNo": cint(page_no), "pageSize": cint(page_size)}
    frappe.log_error(f"Requesting T127 page={page_no} size={page_size} for company={company_name}", "Page Skip Debug")
    success, response = make_post(
        interfaceCode="T127",
        content=payload,
        company_name=company_name,
    )

    if not success:
        frappe.log_error(f"Page {page_no} request failed: {response}", "Page Skip Debug")
        return [], {}

    # Response can be either:
    # A) {"message": {"records": [...], "page": {...}}}
    # B) {"records": [...], "page": {...}}   (already the message)
    if isinstance(response, dict) and "message" in response and isinstance(response["message"], dict):
        msg = response["message"]
    else:
        msg = response or {}

    records = msg.get("records", []) or []
    page_info = msg.get("page", {}) or {}

    frappe.log_error(f"T127 page response page={page_no} got={len(records)} page_info={page_info}", "Page Skip Debug")
    return records, page_info

# ─────────────────────────────────────────────────────
# Create item (minimal fields; safe duplicate check)
# ─────────────────────────────────────────────────────
def create_simple_item(rec, company_name):
    # ----------------------------------------------------------------------
    # 1️⃣ Extract EFRIS fields
    # ----------------------------------------------------------------------
    code = (rec.get("goodsCode") or "").strip()

    if not code:
        frappe.log_error(
            "create_simple_item: Received empty goodsCode. Skipping.",
            "Page Skip Debug"
        )
        return False

    frappe.log_error(
        f"create_simple_item START: goodsCode={code}, company={company_name}",
        "Page Skip Debug"
    )

    # ----------------------------------------------------------------------
    # 2️⃣ Detect if goodsCode is numeric-only
    # ----------------------------------------------------------------------
    is_numeric_code = code.isdigit()
    frappe.log_error(
        f"goodsCode={code}, is_numeric_code={is_numeric_code}",
        "Page Skip Debug"
    )

    # ----------------------------------------------------------------------
    # 3️⃣ Fetch Company Abbreviation
    # ----------------------------------------------------------------------
    company_abbr = frappe.db.get_value("Company", company_name, "abbr")
    frappe.log_error(
        f"company_abbr lookup: company={company_name}, abbr={company_abbr}",
        "Page Skip Debug"
    )

    if not company_abbr:
        frappe.log_error(
            f"⚠️ Company Abbreviation NOT FOUND for company={company_name}. Using fallback = company_name.",
            "Page Skip Debug"
        )
        company_abbr = company_name.replace(" ", "")[:4].upper()

    # ----------------------------------------------------------------------
    # 4️⃣ Build ERPNext document.name (item.name)
    # ----------------------------------------------------------------------
    if is_numeric_code:
        # Numeric only → we ADD company prefix
        item_docname = f"{company_abbr}-{code}"
        frappe.log_error(
            f"Prefix rule applied: new item_docname={item_docname}",
            "Page Skip Debug"
        )
    else:
        # Already prefixed (MHS001 etc.)
        item_docname = code
        frappe.log_error(
            f"Prefix NOT applied because code is not numeric. item_docname={item_docname}",
            "Page Skip Debug"
        )

    # ----------------------------------------------------------------------
    # 5️⃣ Prevent duplicate by checking Item.name
    # ----------------------------------------------------------------------
    if frappe.db.exists("Item", item_docname):
        frappe.log_error(
            f"❌ Item already exists with name={item_docname}. SKIPPING.",
            "Page Skip Debug"
        )
        return False

    # ----------------------------------------------------------------------
    # 6️⃣ Create Item Doc
    # ----------------------------------------------------------------------
    item = frappe.new_doc("Item")

    # Set final document name manually
    item.name = item_docname
    item.flags.ignore_mandatory = True
    item.flags.ignore_permissions = True
    item.flags.ignore_validate = True
    item.flags.name_set = True

    # Store original EFRIS goodsCode in item_code
    item.item_code = code

    # Keep name visible
    name = (rec.get("goodsName") or code).strip()
    item.item_name = name
    item.description = name

    # Other required fields
    item.item_group = "Products"
    item.is_stock_item = 1
    item.efris_item = 1
    item.efris_e_company = company_name

    frappe.log_error(
        f"Item doc initialized: name={item_docname}, item_code={code}, item_name={name}",
        "Page Skip Debug"
    )

    # ----------------------------------------------------------------------
    # 7️⃣ Standard Selling Rate
    # ----------------------------------------------------------------------
    stock_unit = frappe.utils.flt(rec.get("stock") or 0)
    selling_rate = frappe.utils.flt(rec.get("unitPrice") or 0)
    item.standard_rate = selling_rate

    frappe.log_error(
        f"Pricing: stock={stock_unit}, selling_rate={selling_rate}",
        "Page Skip Debug"
    )

    # ----------------------------------------------------------------------
    # 8️⃣ UOM Detection using EFRIS UOM Code
    # ----------------------------------------------------------------------
    measure_unit = (rec.get("measureUnit") or "").strip()
    uom_name = None

    if measure_unit:
        uom_name = frappe.db.get_value("UOM", {"efris_uom_code": measure_unit}, "name")
        frappe.log_error(
            f"UOM lookup: efris_uom_code={measure_unit}, result={uom_name}",
            "Page Skip Debug"
        )

    if not uom_name:
        uom_name = "Nos"
        frappe.log_error(
            f"Fallback UOM applied. Using 'Nos'.",
            "Page Skip Debug"
        )

    item.stock_uom = uom_name

    # ----------------------------------------------------------------------
    # 9️⃣ Commodity Code handling
    # ----------------------------------------------------------------------
    commodity_code = (rec.get("commodityCategoryCode") or "").strip()
    commodity_name = (rec.get("commodityCategoryName") or "").strip()

    is_exempt_flag = (str(rec.get("isExempt") or "")).strip()
    tax_rate = str(rec.get("taxRate") or "").strip()

    # Determine tax category
    if is_exempt_flag == "101":
        e_tax_category = "03:C: Exempt (-)"
    elif is_exempt_flag == "102":
        if tax_rate in ["0.18", "18", "18.0"]:
            e_tax_category = "01:A: Standard (18%)"
        elif tax_rate in ["0.0", "0", ""]:
            e_tax_category = "02:B: Zero (0%)"
        else:
            e_tax_category = "01:A: Standard (18%)"
    else:
        e_tax_category = "01:A: Standard (18%)"

    frappe.log_error(
        f"Commodity: code={commodity_code}, name={commodity_name}, tax_cat={e_tax_category}",
        "Page Skip Debug"
    )

    if commodity_code:
        existing_commodity = frappe.db.get_value(
            "EFRIS Commodity Code",
            {"commodity_code": commodity_code},
            "name"
        )

        if not existing_commodity:
            frappe.log_error(
                f"Creating new commodity {commodity_code}",
                "Page Skip Debug"
            )
            commodity_doc = frappe.new_doc("EFRIS Commodity Code")
            commodity_doc.commodity_code = commodity_code
            commodity_doc.commodity_name = commodity_name
            commodity_doc.e_tax_category = e_tax_category
            commodity_doc.insert(ignore_permissions=True)
            frappe.db.commit()
            item.efris_commodity_code = commodity_doc.name
        else:
            frappe.log_error(
                f"Using existing commodity={existing_commodity}",
                "Page Skip Debug"
            )
            item.efris_commodity_code = existing_commodity

    # ----------------------------------------------------------------------
    # 🔟 Assign Item Tax Template (MUST for EFRIS Items!)
    # ----------------------------------------------------------------------
    template = get_tax_template_for_company(company_name, rec)
    frappe.log_error(f"Tax template selected={template}", "Page Skip Debug")

    if not template:
        frappe.log_error(
            f"❌ No Item Tax Template found for item={item_docname}. Insert WILL FAIL.",
            "Page Skip Debug"
        )
    else:
        item.append("taxes", {"item_tax_template": template})
        frappe.log_error(
            f"✔ Added Item Tax Template {template}",
            "Page Skip Debug"
        )

    # ----------------------------------------------------------------------
    # 1️⃣1️⃣ Insert Item
    # ----------------------------------------------------------------------
    try:
        item.insert(ignore_permissions=True)
        frappe.log_error(
            f"✔ Item INSERTED successfully: name={item_docname}, item_code={code}",
            "Page Skip Debug"
        )
    except Exception as e:
        tb = frappe.get_traceback()
        frappe.log_error(
            f"❌ INSERT FAILED for {item_docname}: {e}\nTRACE:\n{tb}",
            "Page Skip Debug"
        )
        return False

    # ----------------------------------------------------------------------
    # 1️⃣2️⃣ Stock Reconciliation (opening stock)
    # ----------------------------------------------------------------------
    if stock_unit > 0:
        frappe.log_error(
            f"Creating Stock Reconciliation: item={item_docname}, qty={stock_unit}, rate={selling_rate}",
            "Page Skip Debug"
        )
        create_stock_reconciliation_for_item(item.name, stock_unit, selling_rate, company_name)

    return True

def create_stock_reconciliation_for_item(item_code, qty, rate, company_name):
    """Creates a Stock Reconciliation document for a single item."""
    try:
        # 1️⃣ Get company abbreviation
        company_abbr = frappe.db.get_value("Company", company_name, "abbr")
        if not company_abbr:
            frappe.log_error(f"Company abbreviation not found for {company_name}", "Page Skip Debug")
            return

        # 2️⃣ Construct expected warehouse name: "Stores - ABBR"
        expected_warehouse_name = f"Stores - {company_abbr}"

        # 3️⃣ Verify warehouse exists
        # try warehouse by warehouse_name field first (some setups store 'Stores' in a custom field)
        warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": f"Stores", "company": company_name}, "name")
        if not warehouse:
            # fallback to direct name match
            warehouse = frappe.db.get_value("Warehouse", {"name": expected_warehouse_name}, "name")

        if not warehouse:
            frappe.log_error(f"Warehouse '{expected_warehouse_name}' not found for {company_name}", "Page Skip Debug")
            return

        # 4️⃣ Create Stock Reconciliation
        stock_recon = frappe.new_doc("Stock Reconciliation")
        stock_recon.company = company_name
        stock_recon.posting_date = now_datetime()
        stock_recon.set_posting_time = 1
        stock_recon.purpose = "Stock Reconciliation"
        stock_recon.custom_stock_movement_description = f"Auto-created from EFRIS Item Sync for {item_code}"

        stock_recon.append("items", {
            "item_code": item_code,
            "warehouse": warehouse,
            "qty": qty,
            "valuation_rate": rate,
        })

        stock_recon.insert(ignore_permissions=True)
        stock_recon.submit()

        frappe.log_error(f"Stock Reconciliation created for item {item_code} qty={qty} warehouse={warehouse}", "Page Skip Debug")

    except Exception as e:
        tb = frappe.get_traceback()
        frappe.log_error(f"Stock Reconciliation failed for {item_code}: {e} trace={tb}", "Page Skip Debug")
