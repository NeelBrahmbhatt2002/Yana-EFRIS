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
        return frappe.get_doc("EFRIS Sync Progress", name)

    # 🧮 auto-initialize based on existing Item records
    existing_items = frappe.db.count("Item", {"efris_e_company": company_name})
    if existing_items:
        page_no = math.floor(existing_items / PAGE_SIZE) + 1
        offset = existing_items % PAGE_SIZE
        frappe.log_error(
            f"Initializing sync progress for {company_name} "
            f"with existing {existing_items} items → page={page_no}, offset={offset}",
            "EFRIS SYNC INIT",
        )
    else:
        page_no, offset = 1, 0

    doc = frappe.new_doc("EFRIS Sync Progress")
    doc.company = company_name
    doc.last_synced_page = page_no
    doc.last_synced_offset = offset
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc

def get_tax_template_for_company(company_name: str, rec: dict):
    """Choose correct Item Tax Template based on EFRIS item details."""
    rate_raw = (rec.get("taxRate") or "").strip()
    title_hint = None

    # Convert to float safely
    try:
        rate_float = float(rate_raw)
    except ValueError:
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
            f"No matching tax template for company={company_name}, rate={rate_raw}, "
            f"title_hint={title_hint}",
            "EFRIS TAX TEMPLATE MISSING"
        )
    else:
        frappe.log_error(f"Template found: {template}", "EFRIS TAX TRACE")

    return template

def update_progress(progress_doc, page_no: int, offset: int):
    """Persist progress (page + offset)."""
    progress_doc.last_synced_page = cint(page_no)
    progress_doc.last_synced_offset = cint(offset)
    progress_doc.save(ignore_permissions=True)
    frappe.db.commit()

# ─────────────────────────────────────────────────────
# Main sync job (incremental, per-company, paginated)
# ─────────────────────────────────────────────────────
def sync_efris_items(company_name: str):
    created_count = 0

    progress = get_or_create_progress(company_name)
    page_no = max(1, cint(progress.last_synced_page) or 1)
    offset = max(0, cint(progress.last_synced_offset) or 0)

    while created_count < MAX_ITEMS_PER_CLICK:
        records, page_info = fetch_efris_items_page(company_name, page_no, PAGE_SIZE)

        # If nothing returned, we are likely past end
        if not records:
            frappe.log_error("No records returned; likely end reached.", "EFRIS SYNC")
            frappe.msgprint({
                "title": __("EFRIS Sync Complete"),
                "indicator": "green",
                "message": __(f"✅ All EFRIS items have been synced successfully for {company_name}.")
            })
            # Mark as complete: set to next page, offset 0
            update_progress(progress, page_no + 1, 0)
            break

        # Guard offset (in case the page is shorter than expected)
        if offset >= len(records):
            # move to next page
            page_no += 1
            offset = 0
            update_progress(progress, page_no, offset)
            # Check if we’re past total pages (if provided)
            page_count = cint((page_info or {}).get("pageCount") or 0)
            if page_count and page_no > page_count:
                frappe.log_error("Reached end of pages; all items synced.", "EFRIS SYNC")
                break
            continue

        # Process from current offset
        i = offset
        while i < len(records) and created_count < MAX_ITEMS_PER_CLICK:
            rec = records[i]

            # Create only if not exists (safe skip)
            code = (rec.get("goodsCode") or "").strip()
            if code and not frappe.db.exists("Item", code):
                try:
                    if create_simple_item(rec,company_name):
                        created_count += 1
                except Exception:
                    frappe.log_error(frappe.get_traceback(), "EFRIS Item Create Failed")

            i += 1

        if created_count >= MAX_ITEMS_PER_CLICK:
            # Stopped mid-page → update offset to next record index
            new_offset = i if i <= len(records) else 0
            update_progress(progress, page_no, new_offset)
            break

        # Finished the whole page; move to next page, reset offset
        page_no += 1
        offset = 0
        update_progress(progress, page_no, offset)

        # Optional: stop if we know we've reached the end
        page_count = cint((page_info or {}).get("pageCount") or 0)
        if page_count and page_no > page_count:
            frappe.log_error("Reached end of pages; all items synced.", "EFRIS SYNC")
            break

    frappe.log_error(
        f"Sync complete for this run. Created: {created_count}. Next start => page {page_no}, offset {offset}",
        "EFRIS SYNC SUMMARY"
    )

# ─────────────────────────────────────────────────────
# Fetch one page from EFRIS
# ─────────────────────────────────────────────────────
def fetch_efris_items_page(company_name: str, page_no: int, page_size: int):
    from uganda_compliance.efris.api_classes.efris_api import make_post

    payload = {"pageNo": cint(page_no), "pageSize": cint(page_size)}
    success, response = make_post(
        interfaceCode="T127",
        content=payload,
        company_name=company_name,
    )

    if not success:
        frappe.log_error(f"Page {page_no}: {response}", "EFRIS T127 FETCH FAILED")
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

    # Keep title short
    frappe.log_error(
        "EFRIS T127 FETCH",
        f"page={page_no} size={page_size} got={len(records)} page_info={page_info}"
    )
    return records, page_info

# ─────────────────────────────────────────────────────
# Create item (minimal fields; safe duplicate check)
# ─────────────────────────────────────────────────────
def create_simple_item(rec,company_name):
    code = (rec.get("goodsCode") or "").strip()
    if not code:
        return False

    if frappe.db.exists("Item", code):
        return False  # already there

    name = (rec.get("goodsName") or code).strip()

    item = frappe.new_doc("Item")
    item.item_code = code
    item.item_name = name
    item.description = name
    item.item_group = "Products"
    item.is_stock_item = 1     # keep non-stock for now; adjust later if needed
    item.efris_item = 1
    item.efris_e_company = company_name

    frappe.log_error(f"Company Found={company_name}")
    stock_unit = frappe.utils.flt(rec.get("stock") or 0)
    selling_rate = frappe.utils.flt(rec.get("unitPrice") or 0)

    # item.opening_stock = stock_unit
    item.standard_rate = selling_rate

     # 2️⃣ Detect Stock UOM using EFRIS UOM Code
    measure_unit = (rec.get("measureUnit") or "").strip()
    uom_name = None

    if measure_unit:
        uom_name = frappe.db.get_value("UOM", {"efris_uom_code": measure_unit}, "name")

    if not uom_name:
        uom_name = "Nos"  # fallback if EFRIS UOM code not found

    item.stock_uom = uom_name

    # 3️⃣ Handle Commodity Code
    commodity_code = (rec.get("commodityCategoryCode") or "").strip()
    commodity_name = (rec.get("commodityCategoryName") or "").strip()

    e_tax_category = None
    tax_rate = str(rec.get("taxRate") or "").strip()

    # Determine E Tax Category from taxRate
    if tax_rate in ["0.18", "18", "18.0"]:
        e_tax_category = "01:A: Standard (18%)"
    elif tax_rate in ["0.0", "0", ""]:
        e_tax_category = "02:B: Zero (0%)"
    else:
        e_tax_category = "03:C: Exempt (-)"  # fallback
    
    if commodity_code:
        existing_commodity = frappe.db.get_value(
            "EFRIS Commodity Code",
            {"commodity_code": commodity_code},
            "name"
        )

        if not existing_commodity:
            commodity_doc = frappe.new_doc("EFRIS Commodity Code")
            commodity_doc.commodity_code = commodity_code
            commodity_doc.commodity_name = commodity_name
            commodity_doc.e_tax_category = e_tax_category
            commodity_doc.insert(ignore_permissions=True)
            frappe.db.commit()

            item.efris_commodity_code = commodity_doc.name
        else:
            item.efris_commodity_code = existing_commodity

    if company_name:
        template = get_tax_template_for_company(company_name, rec)
        if template:
            # Add a row to the child table `taxes`
            item.append("taxes", {
                "item_tax_template": template
            })

    try:
        item.insert(ignore_permissions=True)
        # frappe.log_error(f"INSERTED: {code}", "DEBUG-SYNC")
        # 5️⃣ Handle opening stock via Stock Reconciliation
        if stock_unit > 0:
            create_stock_reconciliation_for_item(item.name, stock_unit, selling_rate, company_name)

        return True
    except Exception as e:
        frappe.log_error(f"INSERT FAILED: {code} | {e}", "DEBUG-SYNC")
        return False

def create_stock_reconciliation_for_item(item_code, qty, rate, company_name):
    """Creates a Stock Reconciliation document for a single item."""
    try:
        # 1️⃣ Get company abbreviation
        company_abbr = frappe.db.get_value("Company", company_name, "abbr")
        if not company_abbr:
            frappe.log_error(f"Company abbreviation not found for {company_name}", "EFRIS STOCK SYNC")
            return

        # 2️⃣ Construct expected warehouse name: "Stores - ABBR"
        expected_warehouse_name = f"Stores - {company_abbr}"

        # 3️⃣ Verify warehouse exists
        warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": f"Stores", "company": company_name}, "name")
        if not warehouse:
            # fallback to direct name match
            warehouse = frappe.db.get_value("Warehouse", {"name": expected_warehouse_name}, "name")

        if not warehouse:
            frappe.log_error(
                f"Warehouse '{expected_warehouse_name}' not found for {company_name}",
                "EFRIS STOCK SYNC"
            )
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

        frappe.log_error(
            f"Stock Reconciliation created for item {item_code} (qty={qty}, rate={rate}, warehouse={warehouse})",
            "EFRIS STOCK SYNC"
        )

    except Exception as e:
        frappe.log_error(f"Stock Reconciliation failed for {item_code}: {e}", "EFRIS STOCK SYNC ERROR")
