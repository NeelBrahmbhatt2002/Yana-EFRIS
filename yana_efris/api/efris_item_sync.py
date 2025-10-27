import frappe
from frappe.utils import cint, now_datetime

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
    """Get or create the per-company progress row."""
    name = frappe.db.get_value("EFRIS Sync Progress", {"company": company_name})
    if name:
        return frappe.get_doc("EFRIS Sync Progress", name)

    # Create with defaults: start at page 1, offset 0
    doc = frappe.new_doc("EFRIS Sync Progress")
    doc.company = company_name
    doc.last_synced_page = 1
    doc.last_synced_offset = 0
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    return doc

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
                    if create_simple_item(rec):
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
def create_simple_item(rec):
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
    item.stock_uom = "Nos"     # keep simple as requested
    item.item_group = "Products"
    item.is_stock_item = 0     # keep non-stock for now; adjust later if needed

    try:
        item.insert(ignore_permissions=True)
        frappe.log_error(f"INSERTED: {code}", "DEBUG-SYNC")
        return True
    except Exception as e:
        frappe.log_error(f"INSERT FAILED: {code} | {e}", "DEBUG-SYNC")
        return False
