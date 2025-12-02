import frappe
from erpnext.accounts.general_ledger import merge_similar_entries

def create_sales_invoice_from_pos(doc, method=None):
    """
    Auto-create Sales Invoice when POS Invoice is submitted.
    Includes logs, duplicate protection, and correct accounting mappings.
    """

    frappe.log_error(f"POS→SI Triggered for {doc.name}", "POS→SI Debug")

    try:
        # ------------------------------------
        # Prevent duplicate SI
        # ------------------------------------
        existing_si = frappe.db.exists("Sales Invoice", {"pos_invoice": doc.name})
        if existing_si:
            frappe.log_error(f"SI {existing_si} already exists for {doc.name}", "POS→SI Duplicate")
            return

        # ------------------------------------
        # Create Sales Invoice
        # ------------------------------------
        si = frappe.new_doc("Sales Invoice")

        # Link POS & SI
        si.pos_invoice = doc.name

        # BASIC FIELDS
        si.customer = doc.customer
        si.company = doc.company
        si.posting_date = doc.posting_date
        si.posting_time = doc.posting_time
        si.due_date = doc.posting_date

        # CRITICAL FIX: PARTY MAPPING
        si.party_type = "Customer"
        si.party = si.customer

        frappe.log_error(
            f"Basic Fields → customer={si.customer}, party_type={si.party_type}, party={si.party}",
            "POS→SI DEBUG"
        )

        # PAYMENT DETAILS
        si.custom_payment_types = doc.get("custom_payment_types") or doc.get("payment_types")
        si.pos_profile = doc.pos_profile
        si.is_return = doc.is_return
        si.taxes_and_charges = doc.taxes_and_charges

        # ------------------------------------
        # ITEMS
        # ------------------------------------
        for item in doc.items:
            si.append("items", {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "qty": item.qty,
                "rate": item.rate,
                "net_rate": item.net_rate,
                "net_amount": item.net_amount,
                "price_list_rate": item.rate,
                "base_price_list_rate": item.rate,
                "margin_type": "",
                "margin_rate_or_amount": 0,
                "warehouse": item.warehouse,
                "uom": item.uom,
                "discount_percentage": item.discount_percentage,
                "discount_amount": item.discount_amount,
                "distributed_discount_amount": item.get("distributed_discount_amount"),
            })

        frappe.log_error(f"Items Added: {len(si.items)}", "POS→SI DEBUG Items")

        # ------------------------------------
        # TAXES
        # ------------------------------------
        for tax in doc.taxes:
            si.append("taxes", {
                "charge_type": tax.charge_type,
                "account_head": tax.account_head,
                "rate": tax.rate,
                "tax_amount": tax.tax_amount,
                "description": tax.description
            })

        frappe.log_error(f"Taxes Added: {len(si.taxes)}", "POS→SI DEBUG Taxes")

        # ------------------------------------
        # PAYMENTS
        # ------------------------------------
        for p in doc.payments:
            si.append("payments", {
                "mode_of_payment": p.mode_of_payment,
                "amount": p.amount
            })

        si.paid_amount = doc.paid_amount
        si.change_amount = doc.change_amount
        si.account_for_change_amount = doc.account_for_change_amount
        si.update_stock = 0

        frappe.log_error(f"Payments Added: {len(si.payments)}", "POS→SI DEBUG Payments")

        # ------------------------------------
        # INTERNAL ERPNext PREPARATION
        # ------------------------------------
        frappe.log_error("Calling set_missing_values()", "POS→SI DEBUG Internals")
        si.run_method("set_missing_values")

        frappe.log_error("Calling calculate_taxes_and_totals()", "POS→SI DEBUG Internals")
        si.run_method("calculate_taxes_and_totals")

        # Debug accounting fields
        frappe.log_error(
            f"After Internals → debit_to={si.debit_to}, party_type={si.party_type}, party={si.party}",
            "POS→SI DEBUG Accounting Fields"
        )

        # ------------------------------------
        # GL PREVIEW BEFORE SUBMIT
        # ------------------------------------
        try:
            gl_preview = si.get_gl_entries()
            for gl in gl_preview:
                frappe.log_error(
                    f"GL PREVIEW → account={gl.account}, account_type={gl.account_type}, "
                    f"party_type={gl.party_type}, party={gl.party}, debit={gl.debit}, credit={gl.credit}",
                    "POS→SI DEBUG GL ENTRIES"
                )
        except Exception:
            frappe.log_error(f"GL PREVIEW ERROR → {frappe.get_traceback()}", "POS→SI DEBUG")

        # ------------------------------------
        # SAVE → SUBMIT (NO RELOAD, NO SAVE AGAIN)
        # ------------------------------------
        # 1️⃣ INSERT
        si.insert(ignore_permissions=True)

        # 2️⃣ ALLOW ERPNEXT / UGANDA COMPLIANCE TO MODIFY THE DOC
        frappe.db.commit()
        si.reload()

        # 3️⃣ SAVE AGAIN AFTER MODIFICATIONS
        si.save()
        frappe.db.commit()

        # 4️⃣ NOW SUBMIT SAFELY
        si.submit()

        # 5️⃣ AUTO-SUBMIT TO EFRIS
        try:
            from uganda_compliance.efris.api_classes.e_invoice import send_to_efris
            send_to_efris(doc=si)  # Passing frappe Document is valid & recommended
            frappe.log_error(f"EFRIS Submission Successful → {si.name}", "POS→SI→EFRIS")
        except Exception:
            frappe.log_error(f"EFRIS Submission Failed → {frappe.get_traceback()}", "POS→SI→EFRIS ERROR")


        frappe.log_error(f"SI submitted successfully: {si.name}", "POS→SI SUCCESS")

    except Exception:
        frappe.log_error(
            f"Failed to create or submit Sales Invoice\nError: {frappe.get_traceback()}",
            "POS→SI ERROR"
        )
