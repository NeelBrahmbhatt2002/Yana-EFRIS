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

def get_company_fiscal_year(company):
    today = getdate()

    fiscal_year = frappe.db.sql(
        """
        SELECT
            fy.name,
            fy.year_start_date,
            fy.year_end_date
        FROM `tabFiscal Year` fy
        INNER JOIN `tabFiscal Year Company` fyc
            ON fy.name = fyc.parent
        WHERE
            fy.disabled = 0
            AND fyc.company = %s
            AND %s BETWEEN fy.year_start_date AND fy.year_end_date
        LIMIT 1
        """,
        (
            company,
            today,
        ),
        as_dict=True,
    )

    if not fiscal_year:
        frappe.throw(
            _("No active Fiscal Year found for company {0}.").format(company)
        )

    fiscal_year = fiscal_year[0]

    start_year = fiscal_year.year_start_date.year
    end_year = fiscal_year.year_end_date.year % 100

    fiscal_year["display_name"] = f"FY {start_year}-{end_year:02d}"

    return fiscal_year

def get_currency_symbol(companies):
    """
    Returns the currency symbol of the first allowed company.
    Falls back to the currency code if symbol is not configured.
    """
    if not companies:
        return ""

    company = companies[0]

    currency = frappe.db.get_value(
        "Company",
        company,
        "default_currency"
    )

    if not currency:
        return ""

    symbol = frappe.db.get_value(
        "Currency",
        currency,
        "symbol"
    )

    return symbol or currency

@frappe.whitelist()
def get_supplier_summary():

    companies = get_allowed_companies()

    if not companies:
        return {
            "currency_symbol": "",
            "rows": [],
            "totals": {
                "purchase_order_count": 0,
                "purchase_order_amount": 0,
                "purchase_invoice_count": 0,
                "purchase_invoice_amount": 0,
            },
        }

    # Current / active company
    company = frappe.defaults.get_user_default("Company")

    if company not in companies:
        company = companies[0]

    # Current fiscal year for the selected company
    fiscal_year = get_company_fiscal_year(company)

    from_date = fiscal_year["year_start_date"]
    to_date = getdate()

    # Currency
    currency_symbol = get_currency_symbol([company])

    summary = {}

    # Open Purchase Orders
    add_open_purchase_order_summary(
        summary,
        company,
        from_date,
        to_date
    )

    # Unpaid Purchase Invoices
    add_unpaid_purchase_invoice_summary(
        summary,
        company,
        from_date,
        to_date
    )

    # Sort suppliers alphabetically
    rows = sorted(
        summary.values(),
        key=lambda x: x["supplier"]
    )

    # Overall totals
    totals = get_supplier_totals(
        company,
        from_date,
        to_date
    )

    return {
        "currency_symbol": currency_symbol,
        "rows": rows,
        "totals": totals,
    }


# =========================================================
# OPEN PURCHASE ORDER SUMMARY
# =========================================================

def add_open_purchase_order_summary(
    summary,
    company,
    from_date,
    to_date
):

    result = frappe.db.sql(
        """
        SELECT
            supplier,
            COUNT(name),
            COALESCE(SUM(base_net_total), 0)
        FROM `tabPurchase Order`
        WHERE
            docstatus = 1
            AND status IN (
                'To Receive and Bill',
                'To Bill',
                'To Receive'
            )
            AND company = %(company)s
            AND transaction_date BETWEEN %(from_date)s AND %(to_date)s
            AND supplier IS NOT NULL
            AND supplier != ''
        GROUP BY supplier
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )

    for supplier, count, amount in result:

        if supplier not in summary:
            summary[supplier] = get_empty_supplier_row(
                supplier
            )

        summary[supplier]["purchase_order_count"] = count

        summary[supplier]["purchase_order_amount"] = float(
            amount or 0
        )


# =========================================================
# UNPAID PURCHASE INVOICE SUMMARY
# =========================================================

def add_unpaid_purchase_invoice_summary(
    summary,
    company,
    from_date,
    to_date
):

    result = frappe.db.sql(
        """
        SELECT
            supplier,
            COUNT(name),
            COALESCE(SUM(base_net_total), 0)
        FROM `tabPurchase Invoice`
        WHERE
            docstatus = 1
            AND status IN (
                'Unpaid',
                'Partly Paid',
                'Overdue'
            )
            AND company = %(company)s
            AND posting_date BETWEEN %(from_date)s AND %(to_date)s
            AND supplier IS NOT NULL
            AND supplier != ''
        GROUP BY supplier
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )

    for supplier, count, amount in result:

        if supplier not in summary:
            summary[supplier] = get_empty_supplier_row(
                supplier
            )

        summary[supplier]["purchase_invoice_count"] = count

        summary[supplier]["purchase_invoice_amount"] = float(
            amount or 0
        )


# =========================================================
# SUPPLIER TOTALS
# =========================================================

def get_supplier_totals(
    company,
    from_date,
    to_date
):

    purchase_order = frappe.db.sql(
        """
        SELECT
            COUNT(name),
            COALESCE(SUM(base_net_total), 0)
        FROM `tabPurchase Order`
        WHERE
            docstatus = 1
            AND status IN (
                'To Receive and Bill',
                'To Bill',
                'To Receive'
            )
            AND company = %(company)s
            AND transaction_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )[0]

    purchase_invoice = frappe.db.sql(
        """
        SELECT
            COUNT(name),
            COALESCE(SUM(base_net_total), 0)
        FROM `tabPurchase Invoice`
        WHERE
            docstatus = 1
            AND status IN (
                'Unpaid',
                'Partly Paid',
                'Overdue'
            )
            AND company = %(company)s
            AND posting_date BETWEEN %(from_date)s AND %(to_date)s
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )[0]

    return {
        "purchase_order_count": purchase_order[0] or 0,
        "purchase_order_amount": flt(
            purchase_order[1]
        ),

        "purchase_invoice_count": purchase_invoice[0] or 0,
        "purchase_invoice_amount": flt(
            purchase_invoice[1]
        ),
    }


# =========================================================
# EMPTY SUPPLIER ROW
# =========================================================

def get_empty_supplier_row(supplier):

    return {
        "supplier": supplier,

        "purchase_order_count": 0,
        "purchase_order_amount": 0,

        "purchase_invoice_count": 0,
        "purchase_invoice_amount": 0,
    }

@frappe.whitelist()
def get_purchase_receipt_performance():

    companies = get_allowed_companies()

    if not companies:
        return {
            "currency_symbol": "",
            "rows": [],
            "totals": {
                "purchase_order_count": 0,
                "receipt_count": 0,
                "received_amount": 0,
                "pending_po_count": 0,
                "completion_percent": 0,
            },
        }

    # =========================================================
    # CURRENT / ACTIVE COMPANY
    # =========================================================

    company = frappe.defaults.get_user_default("Company")

    if company not in companies:
        company = companies[0]

    # =========================================================
    # CURRENT FISCAL YEAR
    # =========================================================

    fiscal_year = get_company_fiscal_year(company)

    from_date = fiscal_year["year_start_date"]
    to_date = getdate()

    # =========================================================
    # CURRENCY
    # =========================================================

    currency_symbol = get_currency_symbol([company])

    summary = {}

    # =========================================================
    # PURCHASE ORDER SUMMARY
    # =========================================================

    add_purchase_order_performance_summary(
        summary,
        company,
        from_date,
        to_date
    )

    # =========================================================
    # PURCHASE RECEIPT SUMMARY
    # =========================================================

    add_purchase_receipt_performance_summary(
        summary,
        company,
        from_date,
        to_date
    )

    # =========================================================
    # COMPLETION %
    # =========================================================

    calculate_supplier_completion_percent(summary)

    # =========================================================
    # SORT SUPPLIERS
    # =========================================================

    rows = sorted(
        summary.values(),
        key=lambda x: x["supplier"]
    )

    # =========================================================
    # TOTALS
    # =========================================================

    totals = get_purchase_receipt_performance_totals(
        company,
        from_date,
        to_date
    )

    return {
        "currency_symbol": currency_symbol,
        "rows": rows,
        "totals": totals,
    }


# =========================================================
# PURCHASE ORDER PERFORMANCE SUMMARY
# =========================================================

def add_purchase_order_performance_summary(
    summary,
    company,
    from_date,
    to_date
):

    result = frappe.db.sql(
        """
        SELECT
            po.supplier,
            COUNT(DISTINCT po.name) AS purchase_order_count,
            COUNT(
                DISTINCT CASE
                    WHEN po.per_received < 100
                    THEN po.name
                END
            ) AS pending_po_count,
            COALESCE(SUM(poi.qty), 0) AS ordered_qty,
            COALESCE(SUM(poi.received_qty), 0) AS received_qty
        FROM `tabPurchase Order` po
        INNER JOIN `tabPurchase Order Item` poi
            ON poi.parent = po.name
            AND poi.parenttype = 'Purchase Order'
        WHERE
            po.docstatus = 1
            AND po.company = %(company)s
            AND po.transaction_date BETWEEN %(from_date)s
                AND %(to_date)s
            AND po.supplier IS NOT NULL
            AND po.supplier != ''
        GROUP BY po.supplier
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
        as_dict=True,
    )

    for row in result:

        supplier = row.supplier

        if supplier not in summary:
            summary[supplier] = get_empty_purchase_receipt_row(
                supplier
            )

        summary[supplier]["purchase_order_count"] = (
            row.purchase_order_count or 0
        )

        summary[supplier]["pending_po_count"] = (
            row.pending_po_count or 0
        )

        summary[supplier]["ordered_qty"] = float(
            row.ordered_qty or 0
        )

        summary[supplier]["received_qty"] = float(
            row.received_qty or 0
        )


# =========================================================
# PURCHASE RECEIPT PERFORMANCE SUMMARY
# =========================================================

def add_purchase_receipt_performance_summary(
    summary,
    company,
    from_date,
    to_date
):

    result = frappe.db.sql(
        """
        SELECT
            pr.supplier,
            COUNT(DISTINCT pr.name) AS receipt_count,
            COALESCE(SUM(pr.base_net_total), 0) AS received_amount
        FROM `tabPurchase Receipt` pr
        WHERE
            pr.docstatus = 1
            AND pr.company = %(company)s
            AND pr.posting_date BETWEEN %(from_date)s
                AND %(to_date)s
            AND pr.supplier IS NOT NULL
            AND pr.supplier != ''
            AND pr.is_return = 0
        GROUP BY pr.supplier
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
        as_dict=True,
    )

    for row in result:

        supplier = row.supplier

        if supplier not in summary:
            summary[supplier] = get_empty_purchase_receipt_row(
                supplier
            )

        summary[supplier]["receipt_count"] = (
            row.receipt_count or 0
        )

        summary[supplier]["received_amount"] = float(
            row.received_amount or 0
        )


# =========================================================
# COMPLETION PERCENTAGE
# =========================================================

def calculate_supplier_completion_percent(summary):

    for row in summary.values():

        ordered_qty = row.get("ordered_qty", 0)
        received_qty = row.get("received_qty", 0)

        if ordered_qty > 0:

            completion = (
                received_qty / ordered_qty
            ) * 100

            # Prevent percentage from exceeding 100
            completion = min(completion, 100)

        else:
            completion = 0

        row["completion_percent"] = round(
            completion,
            2
        )

        # Internal calculation fields are not required
        # by the frontend.
        row.pop("ordered_qty", None)
        row.pop("received_qty", None)


# =========================================================
# TOTALS
# =========================================================

def get_purchase_receipt_performance_totals(
    company,
    from_date,
    to_date
):

    purchase_order = frappe.db.sql(
        """
        SELECT
            COUNT(name),
            SUM(
                CASE
                    WHEN per_received < 100
                    THEN 1
                    ELSE 0
                END
            )
        FROM `tabPurchase Order`
        WHERE
            docstatus = 1
            AND company = %(company)s
            AND transaction_date BETWEEN %(from_date)s
                AND %(to_date)s
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )[0]

    receipt = frappe.db.sql(
        """
        SELECT
            COUNT(name),
            COALESCE(SUM(base_net_total), 0)
        FROM `tabPurchase Receipt`
        WHERE
            docstatus = 1
            AND company = %(company)s
            AND posting_date BETWEEN %(from_date)s
                AND %(to_date)s
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )[0]

    # =========================================================
    # OVERALL COMPLETION %
    # =========================================================

    quantity = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(poi.qty), 0),
            COALESCE(SUM(poi.received_qty), 0)
        FROM `tabPurchase Order` po
        INNER JOIN `tabPurchase Order Item` poi
            ON poi.parent = po.name
            AND poi.parenttype = 'Purchase Order'
        WHERE
            po.docstatus = 1
            AND po.company = %(company)s
            AND po.transaction_date BETWEEN %(from_date)s
                AND %(to_date)s
        """,
        {
            "company": company,
            "from_date": from_date,
            "to_date": to_date,
        },
    )[0]

    ordered_qty = float(quantity[0] or 0)
    received_qty = float(quantity[1] or 0)

    if ordered_qty > 0:

        completion_percent = (
            received_qty / ordered_qty
        ) * 100

        completion_percent = min(
            completion_percent,
            100
        )

    else:
        completion_percent = 0

    return {
        "purchase_order_count": purchase_order[0] or 0,

        "receipt_count": receipt[0] or 0,

        "received_amount": flt(
            receipt[1]
        ),

        "pending_po_count": purchase_order[1] or 0,

        "completion_percent": round(
            completion_percent,
            2
        ),
    }


# =========================================================
# EMPTY SUPPLIER ROW
# =========================================================

def get_empty_purchase_receipt_row(supplier):

    return {
        "supplier": supplier,

        "purchase_order_count": 0,

        "receipt_count": 0,

        "received_amount": 0,

        "pending_po_count": 0,

        "completion_percent": 0,

        # Internal fields used for calculation
        "ordered_qty": 0,
        "received_qty": 0,
    }

@frappe.whitelist()
def get_purchase_invoice_payables_overview():

    companies = get_allowed_companies()

    currency_symbol = get_currency_symbol(companies)

    if not companies:
        return {
            "currency_symbol": "",
            "rows": [],
            "totals": {
                "invoice_count": 0,
                "invoice_amount": 0,
                "paid": 0,
                "outstanding": 0,
                "overdue": 0,
            },
        }

    # ---------------------------------------------------------
    # Current / Default Company
    # ---------------------------------------------------------

    company = frappe.defaults.get_user_default("Company")

    if company not in companies:
        company = companies[0]

    # ---------------------------------------------------------
    # Current Fiscal Year
    # ---------------------------------------------------------

    fiscal_year = get_company_fiscal_year(company)

    fiscal_year_start = fiscal_year["year_start_date"]
    fiscal_year_end = fiscal_year["year_end_date"]

    summary = {}

    # ---------------------------------------------------------
    # Purchase Invoice Summary
    # ---------------------------------------------------------

    add_purchase_invoice_payables_summary(
        summary,
        company,
        fiscal_year_start,
        fiscal_year_end,
    )

    # ---------------------------------------------------------
    # Sort Suppliers Alphabetically
    # ---------------------------------------------------------

    rows = sorted(
        summary.values(),
        key=lambda x: x["supplier"]
    )

    # ---------------------------------------------------------
    # Totals
    # ---------------------------------------------------------

    totals = get_purchase_invoice_payables_totals(
        company,
        fiscal_year_start,
        fiscal_year_end,
    )

    return {
        "currency_symbol": currency_symbol,
        "rows": rows,
        "totals": totals,
    }


def add_purchase_invoice_payables_summary(
    summary,
    company,
    fiscal_year_start,
    fiscal_year_end,
):

    result = frappe.db.sql(
        """
        SELECT
            supplier,
            status,
            COUNT(name) AS invoice_count,
            COALESCE(SUM(base_net_total), 0) AS invoice_amount
        FROM `tabPurchase Invoice`
        WHERE
            docstatus = 1
            AND company = %s
            AND posting_date BETWEEN %s AND %s
            AND supplier IS NOT NULL
            AND supplier != ''
        GROUP BY
            supplier,
            status
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    for row in result:

        supplier = row.supplier
        status = row.status
        count = row.invoice_count or 0
        amount = float(row.invoice_amount or 0)

        if supplier not in summary:
            summary[supplier] = get_empty_purchase_invoice_row(
                supplier
            )

        # -----------------------------------------------------
        # Total Invoice Count / Amount
        # -----------------------------------------------------

        summary[supplier]["invoice_count"] += count
        summary[supplier]["invoice_amount"] += amount

        # -----------------------------------------------------
        # Paid
        #
        # Same principle as Purchase Invoice tracker:
        # Paid status = Paid amount
        # -----------------------------------------------------

        if status == "Paid":

            summary[supplier]["paid"] += amount

        # -----------------------------------------------------
        # Outstanding
        #
        # Unpaid + Partly Paid + Overdue
        # -----------------------------------------------------

        elif status in (
            "Unpaid",
            "Partly Paid",
            "Overdue",
        ):

            summary[supplier]["outstanding"] += amount

        # -----------------------------------------------------
        # Overdue
        # -----------------------------------------------------

        if status == "Overdue":

            summary[supplier]["overdue"] += amount


def get_purchase_invoice_payables_totals(
    company,
    fiscal_year_start,
    fiscal_year_end,
):

    result = frappe.db.sql(
        """
        SELECT
            COUNT(name) AS invoice_count,

            COALESCE(
                SUM(base_net_total),
                0
            ) AS invoice_amount,

            COALESCE(
                SUM(
                    CASE
                        WHEN status = 'Paid'
                        THEN base_net_total
                        ELSE 0
                    END
                ),
                0
            ) AS paid,

            COALESCE(
                SUM(
                    CASE
                        WHEN status IN (
                            'Unpaid',
                            'Partly Paid',
                            'Overdue'
                        )
                        THEN base_net_total
                        ELSE 0
                    END
                ),
                0
            ) AS outstanding,

            COALESCE(
                SUM(
                    CASE
                        WHEN status = 'Overdue'
                        THEN base_net_total
                        ELSE 0
                    END
                ),
                0
            ) AS overdue

        FROM `tabPurchase Invoice`

        WHERE
            docstatus = 1
            AND company = %s
            AND posting_date BETWEEN %s AND %s
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    row = result[0]

    return {
        "invoice_count": row.invoice_count or 0,
        "invoice_amount": flt(row.invoice_amount),
        "paid": flt(row.paid),
        "outstanding": flt(row.outstanding),
        "overdue": flt(row.overdue),
    }


def get_empty_purchase_invoice_row(supplier):

    return {
        "supplier": supplier,

        "invoice_count": 0,
        "invoice_amount": 0,

        "paid": 0,
        "outstanding": 0,
        "overdue": 0,
    }

@frappe.whitelist()
def get_monthly_purchase_trend():

    companies = get_allowed_companies()

    currency_symbol = get_currency_symbol(companies)

    if not companies:
        return {
            "currency_symbol": "",
            "rows": [],
            "totals": {
                "purchase_order_count": 0,
                "purchase_order_amount": 0,
                "purchase_invoice_count": 0,
                "purchase_invoice_amount": 0,
            },
        }

    company = frappe.defaults.get_user_default("Company")

    if company not in companies:
        company = companies[0]

    fiscal_year = get_company_fiscal_year(company)

    fiscal_year_start = fiscal_year["year_start_date"]
    fiscal_year_end = fiscal_year["year_end_date"]

    rows = build_monthly_purchase_trend_rows(
        fiscal_year_start,
        fiscal_year_end,
    )

    add_purchase_order_monthly_data(
        rows,
        company,
        fiscal_year_start,
        fiscal_year_end,
    )

    add_purchase_invoice_monthly_data(
        rows,
        company,
        fiscal_year_start,
        fiscal_year_end,
    )

    totals = get_monthly_purchase_trend_totals(rows)

    return {
        "currency_symbol": currency_symbol,
        "rows": rows,
        "totals": totals,
    }


def build_monthly_purchase_trend_rows(
    fiscal_year_start,
    fiscal_year_end,
):

    rows = []

    today = getdate()

    current_year = fiscal_year_start.year
    current_month = fiscal_year_start.month

    # Show months only up to the current month
    end_year = today.year
    end_month = today.month

    while True:

        month_key = f"{current_year:04d}-{current_month:02d}"

        month_name = frappe.utils.getdate(
            f"{current_year:04d}-{current_month:02d}-01"
        ).strftime("%B")

        rows.append({
            "month": month_name,
            "month_key": month_key,
            "purchase_order_count": 0,
            "purchase_order_amount": 0,
            "purchase_invoice_count": 0,
            "purchase_invoice_amount": 0,
        })

        # Stop once we reach the current month
        if (
            current_year == end_year
            and current_month == end_month
        ):
            break

        current_month += 1

        if current_month > 12:
            current_month = 1
            current_year += 1

    return rows


def add_purchase_order_monthly_data(
    rows,
    company,
    fiscal_year_start,
    fiscal_year_end,
):

    result = frappe.db.sql(
        """
        SELECT
            YEAR(transaction_date) AS transaction_year,
            MONTH(transaction_date) AS transaction_month,
            COUNT(name) AS purchase_order_count,
            COALESCE(
                SUM(base_net_total),
                0
            ) AS purchase_order_amount

        FROM `tabPurchase Order`

        WHERE
            docstatus = 1
            AND company = %s
            AND transaction_date BETWEEN %s AND %s

        GROUP BY
            YEAR(transaction_date),
            MONTH(transaction_date)
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    data = {
        f"{row.transaction_year:04d}-{row.transaction_month:02d}": row
        for row in result
    }

    for row in rows:

        data_row = data.get(row["month_key"])

        if not data_row:
            continue

        row["purchase_order_count"] = (
            data_row.purchase_order_count or 0
        )

        row["purchase_order_amount"] = float(
            data_row.purchase_order_amount or 0
        )


def add_purchase_invoice_monthly_data(
    rows,
    company,
    fiscal_year_start,
    fiscal_year_end,
):

    result = frappe.db.sql(
        """
        SELECT
            YEAR(posting_date) AS transaction_year,
            MONTH(posting_date) AS transaction_month,
            COUNT(name) AS purchase_invoice_count,
            COALESCE(
                SUM(base_net_total),
                0
            ) AS purchase_invoice_amount

        FROM `tabPurchase Invoice`

        WHERE
            docstatus = 1
            AND company = %s
            AND posting_date BETWEEN %s AND %s

        GROUP BY
            YEAR(posting_date),
            MONTH(posting_date)
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    data = {
        f"{row.transaction_year:04d}-{row.transaction_month:02d}": row
        for row in result
    }

    for row in rows:

        data_row = data.get(row["month_key"])

        if not data_row:
            continue

        row["purchase_invoice_count"] = (
            data_row.purchase_invoice_count or 0
        )

        row["purchase_invoice_amount"] = float(
            data_row.purchase_invoice_amount or 0
        )


def get_monthly_purchase_trend_totals(rows):

    return {
        "purchase_order_count": sum(
            row["purchase_order_count"]
            for row in rows
        ),

        "purchase_order_amount": flt(
            sum(
                row["purchase_order_amount"]
                for row in rows
            )
        ),

        "purchase_invoice_count": sum(
            row["purchase_invoice_count"]
            for row in rows
        ),

        "purchase_invoice_amount": flt(
            sum(
                row["purchase_invoice_amount"]
                for row in rows
            )
        ),
    }

@frappe.whitelist()
def get_top_purchased_items():

    companies = get_allowed_companies()

    currency_symbol = get_currency_symbol(companies)

    if not companies:
        return {
            "currency_symbol": "",
            "rows": [],
            "totals": {
                "purchase_amount": 0,
            },
        }

    company = frappe.defaults.get_user_default("Company")

    if company not in companies:
        company = companies[0]

    fiscal_year = get_company_fiscal_year(company)

    fiscal_year_start = fiscal_year["year_start_date"]
    fiscal_year_end = fiscal_year["year_end_date"]

    total_purchase_amount = get_total_purchase_amount(
        company,
        fiscal_year_start,
        fiscal_year_end,
    )

    rows = get_top_purchased_item_rows(
        company,
        fiscal_year_start,
        fiscal_year_end,
        total_purchase_amount,
    )

    return {
        "currency_symbol": currency_symbol,
        "rows": rows,
        "totals": {
            "purchase_amount": flt(total_purchase_amount),
        },
    }


def get_top_purchased_item_rows(
    company,
    fiscal_year_start,
    fiscal_year_end,
    total_purchase_amount,
):

    result = frappe.db.sql(
        """
        SELECT
            pii.item_code,
            pii.item_name,
            COALESCE(
                SUM(pii.qty),
                0
            ) AS qty_purchased,
            COALESCE(
                SUM(pii.base_net_amount),
                0
            ) AS purchase_amount

        FROM `tabPurchase Invoice Item` pii

        INNER JOIN `tabPurchase Invoice` pi
            ON pi.name = pii.parent

        WHERE
            pi.docstatus = 1
            AND pi.company = %s
            AND pi.posting_date BETWEEN %s AND %s
            AND pii.item_code IS NOT NULL
            AND pii.item_code != ''

        GROUP BY
            pii.item_code,
            pii.item_name

        ORDER BY
            purchase_amount DESC

        LIMIT 20
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    rows = []

    for rank, row in enumerate(result, start=1):

        purchase_amount = flt(
            row.purchase_amount
        )

        if total_purchase_amount:
            contribution = (
                purchase_amount
                / total_purchase_amount
            ) * 100
        else:
            contribution = 0

        rows.append({
            "rank": rank,
            "item": row.item_name or row.item_code,
            "item_code": row.item_code,
            "qty_purchased": flt(
                row.qty_purchased
            ),
            "purchase_amount": purchase_amount,
            "contribution": contribution,
        })

    return rows


def get_total_purchase_amount(
    company,
    fiscal_year_start,
    fiscal_year_end,
):

    result = frappe.db.sql(
        """
        SELECT
            COALESCE(
                SUM(base_net_total),
                0
            ) AS purchase_amount

        FROM `tabPurchase Invoice`

        WHERE
            docstatus = 1
            AND company = %s
            AND posting_date BETWEEN %s AND %s
        """,
        (
            company,
            fiscal_year_start,
            fiscal_year_end,
        ),
        as_dict=True,
    )

    return flt(
        result[0].purchase_amount
    )