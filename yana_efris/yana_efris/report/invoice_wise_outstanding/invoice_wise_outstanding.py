# Copyright (c) 2026, YanaERP and contributors
# For license information, please see license.txt

# import frappe


# def execute(filters=None):
# 	columns, data = [], []
# 	return columns, data


# def execute_snapshot_report(filters: dict | None = None):
# 	"""Return columns and data for the report.

# 	This is the main entry point for snapshot report. When 'Synced
# 	Report' is enabled in report, framework will call this method
# 	every time the report is refreshed or a filter is updated. It
# 	accepts the same filters as normal execute. But a utility method -
# 	get_latest_sync, is also imported.

# 	"""
# 	from frappe.database.duckdb.database import get_latest_sync

# 	columns, data = [], []
# 	return columns, data


import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate


def execute(filters=None):
    filters = frappe._dict(filters or {})
    validate_filters(filters)

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def validate_filters(filters):
    if not filters.get("company"):
        frappe.throw(_("Please select a Company."))

    if not filters.get("as_on_date"):
        filters.as_on_date = nowdate()

    filters.as_on_date = getdate(filters.as_on_date)

    if filters.get("from_date") and filters.get("to_date"):
        if getdate(filters.from_date) > getdate(filters.to_date):
            frappe.throw(_("From Date cannot be after To Date."))



def get_columns():
    return [
        {
            "label": _("Sales Invoice"),
            "fieldname": "invoice",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 180,
        },
        {
            "label": _("Posting Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "label": _("Due Date"),
            "fieldname": "due_date",
            "fieldtype": "Date",
            "width": 105,
        },
        {
            "label": _("Customer"),
            "fieldname": "customer",
            "fieldtype": "Link",
            "options": "Customer",
            "width": 170,
        },
        {
            "label": _("Customer Name"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 200
        },
        {
            "label": _("Invoice Currency"),
            "fieldname": "invoice_currency",
            "fieldtype": "Link",
            "options": "Currency",
            "width": 110,
        },
        {
            "label": _("Invoice Amount (Company Currency)"),
            "fieldname": "invoice_amount",
            "fieldtype": "Currency",
            "options": "company_currency",
            "width": 180,
        },
        {
            "label": _("Payment"),
            "fieldname": "payment",
            "fieldtype": "Currency",
            "options": "company_currency",
            "width": 135,
        },
        {
            "label": _("Deductions"),
            "fieldname": "deductions",
            "fieldtype": "Currency",
            "options": "company_currency",
            "width": 135,
        },
        {
            "label": _("Net Outstanding Balance"),
            "fieldname": "outstanding",
            "fieldtype": "Currency",
            "options": "company_currency",
            "width": 185,
        },
        {
            "label": _("Invoice Age (Days)"),
            "fieldname": "invoice_age",
            "fieldtype": "Int",
            "width": 125,
        },
        {
            "label": _("Days Overdue"),
            "fieldname": "days_overdue",
            "fieldtype": "Int",
            "width": 110,
        },
        {
            "label": _("Ageing Bucket"),
            "fieldname": "ageing_bucket",
            "fieldtype": "Data",
            "width": 120,
        },
    ]



def get_data(filters):
    conditions = [
        "si.docstatus = 1",
        "si.is_return = 0",
        "si.company = %(company)s",
        "si.posting_date <= %(as_on_date)s",
    ]

    if filters.get("customer"):
        conditions.append("si.customer = %(customer)s")

    if filters.get("from_date"):
        conditions.append("si.posting_date >= %(from_date)s")

    if filters.get("to_date"):
        conditions.append("si.posting_date <= %(to_date)s")

    if filters.get("currency"):
        conditions.append("si.currency = %(currency)s")

    invoices = frappe.db.sql(
        """
        SELECT
            si.name AS invoice,
            si.company,
            si.customer,
            c.customer_name AS customer_name,
            si.posting_date,
            si.due_date,
            si.currency AS invoice_currency,
            si.base_grand_total AS invoice_amount,
            si.conversion_rate
        FROM `tabSales Invoice` si
        LEFT JOIN `tabCustomer` c
            ON c.name = si.customer
        WHERE {conditions}
        ORDER BY si.posting_date, si.name
        """.format(conditions=" AND ".join(conditions)),
        filters,
        as_dict=True,
    )

    if not invoices:
        return []

    company_currency = frappe.get_cached_value(
        "Company", filters.company, "default_currency"
    )

    invoice_names = [row.invoice for row in invoices]

    # Get submitted payment allocations for the selected invoices.
    payment_rows = frappe.db.sql(
        """
        SELECT
            per.reference_name AS invoice,
            pe.name AS payment_entry,
            per.allocated_amount
        FROM `tabPayment Entry Reference` per
        INNER JOIN `tabPayment Entry` pe
            ON pe.name = per.parent
        WHERE
            per.reference_doctype = 'Sales Invoice'
            AND per.reference_name IN %(invoice_names)s
            AND pe.company = %(company)s
            AND pe.docstatus = 1
            AND pe.posting_date <= %(as_on_date)s
        ORDER BY pe.posting_date, pe.name
        """,
        {
            "invoice_names": tuple(invoice_names),
            "company": filters.company,
            "as_on_date": filters.as_on_date,
        },
        as_dict=True,
    )

    payments = {}
    payment_entry_names = set()

    for row in payment_rows:
        payments[row.invoice] = (
            payments.get(row.invoice, 0)
            + flt(row.allocated_amount)
        )
        payment_entry_names.add(row.payment_entry)

    # Fetch standard Payment Entry deductions in company currency.
    deduction_by_payment = {}

    if payment_entry_names:
        deduction_rows = frappe.db.sql(
            """
            SELECT
                ped.parent AS payment_entry,
                SUM(ped.amount) AS deduction_amount
            FROM `tabPayment Entry Deduction` ped
            INNER JOIN `tabPayment Entry` pe
                ON pe.name = ped.parent
            WHERE
                ped.parent IN %(payment_entries)s
                AND pe.company = %(company)s
                AND pe.docstatus = 1
                AND pe.posting_date <= %(as_on_date)s
            GROUP BY ped.parent
            """,
            {
                "payment_entries": tuple(payment_entry_names),
                "company": filters.company,
                "as_on_date": filters.as_on_date,
            },
            as_dict=True,
        )

        deduction_by_payment = {
            row.payment_entry: flt(row.deduction_amount)
            for row in deduction_rows
        }

    # Fetch all Sales Invoice references for these payments so
    # deductions can be distributed consistently across invoices.
    refs_by_payment = {}

    if payment_entry_names:
        all_references = frappe.db.sql(
            """
            SELECT
                per.parent AS payment_entry,
                per.reference_name AS invoice,
                per.allocated_amount
            FROM `tabPayment Entry Reference` per
            INNER JOIN `tabPayment Entry` pe
                ON pe.name = per.parent
            WHERE
                per.reference_doctype = 'Sales Invoice'
                AND per.parent IN %(payment_entries)s
                AND pe.company = %(company)s
                AND pe.docstatus = 1
                AND pe.posting_date <= %(as_on_date)s
            """,
            {
                "payment_entries": tuple(payment_entry_names),
                "company": filters.company,
                "as_on_date": filters.as_on_date,
            },
            as_dict=True,
        )

        for ref in all_references:
            refs_by_payment.setdefault(
                ref.payment_entry, []
            ).append(ref)

    deductions = {}

    for payment_entry, references in refs_by_payment.items():
        total_allocated = sum(
            flt(ref.allocated_amount)
            for ref in references
        )
        total_deduction = deduction_by_payment.get(
            payment_entry, 0
        )

        if not total_allocated or not total_deduction:
            continue

        for ref in references:
            if ref.invoice not in invoice_names:
                continue

            share = (
                total_deduction
                * flt(ref.allocated_amount)
                / total_allocated
            )

            deductions[ref.invoice] = (
                deductions.get(ref.invoice, 0) + share
            )

    data = []

    for invoice in invoices:
        # These figures are intended to be in company currency.
        invoice_amount = flt(invoice.invoice_amount)
        payment_amount = flt(payments.get(invoice.invoice, 0))
        deduction_amount = flt(deductions.get(invoice.invoice, 0))

        # Manager's required calculation.
        outstanding = (
            invoice_amount - payment_amount - deduction_amount
        )

        invoice_age = max(
            (
                getdate(filters.as_on_date)
                - getdate(invoice.posting_date)
            ).days,
            0,
        )

        days_overdue = (
            max(
                (
                    getdate(filters.as_on_date)
                    - getdate(invoice.due_date)
                ).days,
                0,
            )
            if invoice.due_date
            else 0
        )

        if days_overdue <= 0:
            ageing_bucket = _("Not Overdue")
        elif days_overdue <= 30:
            ageing_bucket = _("1-30 Days")
        elif days_overdue <= 60:
            ageing_bucket = _("31-60 Days")
        elif days_overdue <= 90:
            ageing_bucket = _("61-90 Days")
        else:
            ageing_bucket = _("90+ Days")

        if abs(outstanding) < 0.005:
            continue

        data.append({
            "invoice": invoice.invoice,
            "posting_date": invoice.posting_date,
            "due_date": invoice.due_date,
            "customer": invoice.customer,
            "customer_name": invoice.customer_name,
            "invoice_currency": invoice.invoice_currency,
            "invoice_amount": invoice_amount,
            "payment": payment_amount,
            "deductions": deduction_amount,
            "outstanding": outstanding,
            "invoice_age": invoice_age,
            "days_overdue": days_overdue,
            "ageing_bucket": ageing_bucket,
            "company_currency": company_currency,
        })

    return data


