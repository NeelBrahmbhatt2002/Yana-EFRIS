import frappe
from frappe import _
from frappe.utils import today, getdate,add_days, add_years, flt
from collections import defaultdict

import json, base64, gzip
from Crypto.Cipher import AES
import frappe
from frappe.utils import cint
from frappe.query_builder import DocType, functions as fn
from frappe.utils import flt, nowdate,now_datetime, formatdate, format_time
from frappe.utils.nestedset import get_root_of
from frappe.utils.pdf import get_pdf
from datetime import date, timedelta
from calendar import monthrange

def get_allowed_companies():
    """
    Returns the active company for the current user.

    If the user has multiple allowed companies, the current
    default company is returned.

    If no User Permissions exist (Administrator), the current
    default company is returned. If no default company exists,
    all companies are returned as a fallback.
    """

    allowed_companies = frappe.get_all(
        "User Permission",
        filters={
            "user": frappe.session.user,
            "allow": "Company",
        },
        pluck="for_value",
    )

    active_company = frappe.defaults.get_user_default("company")

    # User has Company User Permissions
    if allowed_companies:

        # Active company is one of the allowed companies
        if active_company and active_company in allowed_companies:
            return [active_company]

        # Fallback to first allowed company
        return [allowed_companies[0]]

    # Administrator / no company restrictions
    if active_company:
        return [active_company]

    # Final fallback
    return frappe.get_all("Company", pluck="name")


@frappe.whitelist()
def get_material_request_tracker():

    # Get companies available to the current user
    allowed_companies = get_allowed_companies()

    if not allowed_companies:
        return {
            "total_count": 0,
            "currency_symbol": "",
            "draft": {"count": 0, "amount": 0},
            "submitted": {"count": 0, "amount": 0},
            "stopped": {"count": 0, "amount": 0},
            "cancelled": {"count": 0, "amount": 0},
            "pending": {"count": 0, "amount": 0},
            "partially_ordered": {"count": 0, "amount": 0},
            "partially_received": {"count": 0, "amount": 0},
            "ordered": {"count": 0, "amount": 0},
            "issued": {"count": 0, "amount": 0},
            "transferred": {"count": 0, "amount": 0},
            "received": {"count": 0, "amount": 0},
        }

    # Get currently selected/default company
    company = frappe.defaults.get_user_default("Company")

    # Safety fallback
    if company not in allowed_companies:
        company = allowed_companies[0]

    # Get company's default currency
    currency = frappe.db.get_value(
        "Company",
        company,
        "default_currency"
    )

    currency_symbol = ""

    if currency:
        currency_symbol = (
            frappe.db.get_value(
                "Currency",
                currency,
                "symbol"
            )
            or currency
        )

    # Default response
    result = {
        "total_count": 0,
        "currency_symbol": currency_symbol,

        "draft": {
            "count": 0,
            "amount": 0
        },

        "submitted": {
            "count": 0,
            "amount": 0
        },

        "stopped": {
            "count": 0,
            "amount": 0
        },

        "cancelled": {
            "count": 0,
            "amount": 0
        },

        "pending": {
            "count": 0,
            "amount": 0
        },

        "partially_ordered": {
            "count": 0,
            "amount": 0
        },

        "partially_received": {
            "count": 0,
            "amount": 0
        },

        "ordered": {
            "count": 0,
            "amount": 0
        },

        "issued": {
            "count": 0,
            "amount": 0
        },

        "transferred": {
            "count": 0,
            "amount": 0
        },

        "received": {
            "count": 0,
            "amount": 0
        },
    }

    # Fetch Material Request status and total amount
    rows = frappe.db.sql(
        """
        SELECT
            mr.status,
            COUNT(DISTINCT mr.name) AS count,
            COALESCE(SUM(mri.amount), 0) AS amount

        FROM `tabMaterial Request` mr

        LEFT JOIN `tabMaterial Request Item` mri
            ON mri.parent = mr.name
            AND mri.parenttype = 'Material Request'

        WHERE
            mr.company = %s
            AND mr.material_request_type = 'Purchase'

        GROUP BY
            mr.status
        """,
        (company,),
        as_dict=True
    )

    # Map database status to dashboard cards
    for row in rows:

        status = row.status
        count = int(row.count or 0)
        amount = float(row.amount or 0)

        if status == "Draft":
            result["draft"]["count"] = count
            result["draft"]["amount"] = amount

        elif status == "Submitted":
            result["submitted"]["count"] = count
            result["submitted"]["amount"] = amount

        elif status == "Stopped":
            result["stopped"]["count"] = count
            result["stopped"]["amount"] = amount

        elif status == "Cancelled":
            result["cancelled"]["count"] = count
            result["cancelled"]["amount"] = amount

        elif status == "Pending":
            result["pending"]["count"] = count
            result["pending"]["amount"] = amount

        elif status == "Partially Ordered":
            result["partially_ordered"]["count"] = count
            result["partially_ordered"]["amount"] = amount

        elif status == "Partially Received":
            result["partially_received"]["count"] = count
            result["partially_received"]["amount"] = amount

        elif status == "Ordered":
            result["ordered"]["count"] = count
            result["ordered"]["amount"] = amount

        elif status == "Issued":
            result["issued"]["count"] = count
            result["issued"]["amount"] = amount

        elif status == "Transferred":
            result["transferred"]["count"] = count
            result["transferred"]["amount"] = amount

        elif status == "Received":
            result["received"]["count"] = count
            result["received"]["amount"] = amount

    # Total number of Material Requests
    result["total_count"] = sum(
        result[status]["count"]
        for status in [
            "draft",
            "submitted",
            "stopped",
            "cancelled",
            "pending",
            "partially_ordered",
            "partially_received",
            "ordered",
            "issued",
            "transferred",
            "received"
        ]
    )

    return result

@frappe.whitelist()
def get_purchase_order_tracker():

    # Get companies available to the current user
    allowed_companies = get_allowed_companies()

    if not allowed_companies:
        return {
            "total_count": 0,
            "currency_symbol": "",

            "draft": {"count": 0, "amount": 0},
            "on_hold": {"count": 0, "amount": 0},
            "to_receive_and_bill": {"count": 0, "amount": 0},
            "to_bill": {"count": 0, "amount": 0},
            "to_receive": {"count": 0, "amount": 0},
            "completed": {"count": 0, "amount": 0},
            "cancelled": {"count": 0, "amount": 0},
            "closed": {"count": 0, "amount": 0},
            "delivered": {"count": 0, "amount": 0},
        }

    # Get currently selected/default company
    company = frappe.defaults.get_user_default("Company")

    # Safety fallback
    if company not in allowed_companies:
        company = allowed_companies[0]

    # Get company's default currency
    currency = frappe.db.get_value(
        "Company",
        company,
        "default_currency"
    )

    currency_symbol = ""

    if currency:
        currency_symbol = (
            frappe.db.get_value(
                "Currency",
                currency,
                "symbol"
            )
            or currency
        )

    # Default response
    result = {
        "total_count": 0,
        "currency_symbol": currency_symbol,

        "draft": {
            "count": 0,
            "amount": 0
        },

        "on_hold": {
            "count": 0,
            "amount": 0
        },

        "to_receive_and_bill": {
            "count": 0,
            "amount": 0
        },

        "to_bill": {
            "count": 0,
            "amount": 0
        },

        "to_receive": {
            "count": 0,
            "amount": 0
        },

        "completed": {
            "count": 0,
            "amount": 0
        },

        "cancelled": {
            "count": 0,
            "amount": 0
        },

        "closed": {
            "count": 0,
            "amount": 0
        },

        "delivered": {
            "count": 0,
            "amount": 0
        },
    }

    # Fetch Purchase Order status and amount
    #
    # Draft and Cancelled are determined using docstatus
    # to ensure they are always captured correctly.
    #
    # base_net_total is used because the tracker amount
    # should exclude VAT/taxes.
    rows = frappe.db.sql(
        """
        SELECT
            CASE
                WHEN po.docstatus = 0 THEN 'Draft'
                WHEN po.docstatus = 2 THEN 'Cancelled'
                ELSE po.status
            END AS status,

            COUNT(po.name) AS count,

            COALESCE(
                SUM(po.base_net_total),
                0
            ) AS amount

        FROM `tabPurchase Order` po

        WHERE
            po.company = %s

        GROUP BY
            CASE
                WHEN po.docstatus = 0 THEN 'Draft'
                WHEN po.docstatus = 2 THEN 'Cancelled'
                ELSE po.status
            END
        """,
        (company,),
        as_dict=True
    )

    # Map database status to dashboard cards
    for row in rows:

        status = row.status
        count = int(row.count or 0)
        amount = float(row.amount or 0)

        if status == "Draft":
            result["draft"]["count"] = count
            result["draft"]["amount"] = amount

        elif status == "On Hold":
            result["on_hold"]["count"] = count
            result["on_hold"]["amount"] = amount

        elif status == "To Receive and Bill":
            result["to_receive_and_bill"]["count"] = count
            result["to_receive_and_bill"]["amount"] = amount

        elif status == "To Bill":
            result["to_bill"]["count"] = count
            result["to_bill"]["amount"] = amount

        elif status == "To Receive":
            result["to_receive"]["count"] = count
            result["to_receive"]["amount"] = amount

        elif status == "Completed":
            result["completed"]["count"] = count
            result["completed"]["amount"] = amount

        elif status == "Cancelled":
            result["cancelled"]["count"] = count
            result["cancelled"]["amount"] = amount

        elif status == "Closed":
            result["closed"]["count"] = count
            result["closed"]["amount"] = amount

        elif status == "Delivered":
            result["delivered"]["count"] = count
            result["delivered"]["amount"] = amount

    # Total number of Purchase Orders
    result["total_count"] = sum(
        result[status]["count"]
        for status in [
            "draft",
            "on_hold",
            "to_receive_and_bill",
            "to_bill",
            "to_receive",
            "completed",
            "cancelled",
            "closed",
            "delivered"
        ]
    )

    return result

@frappe.whitelist()
def get_purchase_receipt_tracker():

    # Get companies available to the current user
    allowed_companies = get_allowed_companies()

    if not allowed_companies:
        return {
            "total_count": 0,
            "currency_symbol": "",

            "draft": {"count": 0, "amount": 0},
            "partly_billed": {"count": 0, "amount": 0},
            "to_bill": {"count": 0, "amount": 0},
            "completed": {"count": 0, "amount": 0},
            "return": {"count": 0, "amount": 0},
            "return_issued": {"count": 0, "amount": 0},
            "cancelled": {"count": 0, "amount": 0},
            "closed": {"count": 0, "amount": 0},
        }

    # Get currently selected/default company
    company = frappe.defaults.get_user_default("Company")

    # Safety fallback
    if company not in allowed_companies:
        company = allowed_companies[0]

    # Get company's default currency
    currency = frappe.db.get_value(
        "Company",
        company,
        "default_currency"
    )

    currency_symbol = ""

    if currency:
        currency_symbol = (
            frappe.db.get_value(
                "Currency",
                currency,
                "symbol"
            )
            or currency
        )

    # Default response
    result = {
        "total_count": 0,
        "currency_symbol": currency_symbol,

        "draft": {
            "count": 0,
            "amount": 0
        },

        "partly_billed": {
            "count": 0,
            "amount": 0
        },

        "to_bill": {
            "count": 0,
            "amount": 0
        },

        "completed": {
            "count": 0,
            "amount": 0
        },

        "return": {
            "count": 0,
            "amount": 0
        },

        "return_issued": {
            "count": 0,
            "amount": 0
        },

        "cancelled": {
            "count": 0,
            "amount": 0
        },

        "closed": {
            "count": 0,
            "amount": 0
        },
    }

    # Fetch Purchase Receipt status and amount excluding VAT
    rows = frappe.db.sql(
        """
        SELECT
            pr.status,
            COUNT(pr.name) AS count,
            COALESCE(SUM(pr.base_net_total), 0) AS amount

        FROM `tabPurchase Receipt` pr

        WHERE
            pr.company = %s

        GROUP BY
            pr.status
        """,
        (company,),
        as_dict=True
    )

    # Map database status to dashboard cards
    for row in rows:

        status = row.status
        count = int(row.count or 0)
        amount = float(row.amount or 0)

        if status == "Draft":
            result["draft"]["count"] = count
            result["draft"]["amount"] = amount

        elif status == "Partly Billed":
            result["partly_billed"]["count"] = count
            result["partly_billed"]["amount"] = amount

        elif status == "To Bill":
            result["to_bill"]["count"] = count
            result["to_bill"]["amount"] = amount

        elif status == "Completed":
            result["completed"]["count"] = count
            result["completed"]["amount"] = amount

        elif status == "Return":
            result["return"]["count"] = count
            result["return"]["amount"] = amount

        elif status == "Return Issued":
            result["return_issued"]["count"] = count
            result["return_issued"]["amount"] = amount

        elif status == "Cancelled":
            result["cancelled"]["count"] = count
            result["cancelled"]["amount"] = amount

        elif status == "Closed":
            result["closed"]["count"] = count
            result["closed"]["amount"] = amount

    # Total number of Purchase Receipts
    result["total_count"] = sum(
        result[status]["count"]
        for status in [
            "draft",
            "partly_billed",
            "to_bill",
            "completed",
            "return",
            "return_issued",
            "cancelled",
            "closed"
        ]
    )

    return result


@frappe.whitelist()
def get_purchase_invoice_tracker():

    # Get companies available to the current user
    allowed_companies = get_allowed_companies()

    if not allowed_companies:
        return {
            "total_count": 0,
            "currency_symbol": "",

            "draft": {"count": 0, "amount": 0},
            "return": {"count": 0, "amount": 0},
            "debit_note_issued": {"count": 0, "amount": 0},
            "submitted": {"count": 0, "amount": 0},
            "paid": {"count": 0, "amount": 0},
            "partly_paid": {"count": 0, "amount": 0},
            "unpaid": {"count": 0, "amount": 0},
            "overdue": {"count": 0, "amount": 0},
            "cancelled": {"count": 0, "amount": 0},
            "internal_transfer": {"count": 0, "amount": 0},
        }

    # Get currently selected/default company
    company = frappe.defaults.get_user_default("Company")

    # Safety fallback
    if company not in allowed_companies:
        company = allowed_companies[0]

    # Get company's default currency
    currency = frappe.db.get_value(
        "Company",
        company,
        "default_currency"
    )

    currency_symbol = ""

    if currency:
        currency_symbol = (
            frappe.db.get_value(
                "Currency",
                currency,
                "symbol"
            )
            or currency
        )

    # Default response
    result = {
        "total_count": 0,
        "currency_symbol": currency_symbol,

        "draft": {
            "count": 0,
            "amount": 0
        },

        "return": {
            "count": 0,
            "amount": 0
        },

        "debit_note_issued": {
            "count": 0,
            "amount": 0
        },

        "submitted": {
            "count": 0,
            "amount": 0
        },

        "paid": {
            "count": 0,
            "amount": 0
        },

        "partly_paid": {
            "count": 0,
            "amount": 0
        },

        "unpaid": {
            "count": 0,
            "amount": 0
        },

        "overdue": {
            "count": 0,
            "amount": 0
        },

        "cancelled": {
            "count": 0,
            "amount": 0
        },

        "internal_transfer": {
            "count": 0,
            "amount": 0
        },
    }

    # Fetch Purchase Invoice status and total amount
    rows = frappe.db.sql(
        """
        SELECT
            pi.status,
            COUNT(pi.name) AS count,
            COALESCE(SUM(pi.base_net_total), 0) AS amount

        FROM `tabPurchase Invoice` pi

        WHERE
            pi.company = %s

        GROUP BY
            pi.status
        """,
        (company,),
        as_dict=True
    )

    # Map database status to dashboard cards
    for row in rows:

        status = row.status
        count = int(row.count or 0)
        amount = float(row.amount or 0)

        if status == "Draft":
            result["draft"]["count"] = count
            result["draft"]["amount"] = amount

        elif status == "Return":
            result["return"]["count"] = count
            result["return"]["amount"] = amount

        elif status == "Debit Note Issued":
            result["debit_note_issued"]["count"] = count
            result["debit_note_issued"]["amount"] = amount

        elif status == "Submitted":
            result["submitted"]["count"] = count
            result["submitted"]["amount"] = amount

        elif status == "Paid":
            result["paid"]["count"] = count
            result["paid"]["amount"] = amount

        elif status == "Partly Paid":
            result["partly_paid"]["count"] = count
            result["partly_paid"]["amount"] = amount

        elif status == "Unpaid":
            result["unpaid"]["count"] = count
            result["unpaid"]["amount"] = amount

        elif status == "Overdue":
            result["overdue"]["count"] = count
            result["overdue"]["amount"] = amount

        elif status == "Cancelled":
            result["cancelled"]["count"] = count
            result["cancelled"]["amount"] = amount

        elif status == "Internal Transfer":
            result["internal_transfer"]["count"] = count
            result["internal_transfer"]["amount"] = amount

    # Total number of Purchase Invoices
    result["total_count"] = sum(
        result[status]["count"]
        for status in [
            "draft",
            "return",
            "debit_note_issued",
            "submitted",
            "paid",
            "partly_paid",
            "unpaid",
            "overdue",
            "cancelled",
            "internal_transfer"
        ]
    )

    return result