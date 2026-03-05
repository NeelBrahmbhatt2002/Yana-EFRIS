# Copyright (c) 2026, YanaERP and contributors
# For license information, please see license.txt

# import frappe


# def execute(filters=None):
# 	columns, data = [], []
# 	return columns, data

import frappe
from frappe.utils import getdate
from datetime import datetime
from collections import defaultdict

def get_month_list(from_date, to_date):
    from_date = getdate(from_date)
    to_date = getdate(to_date)

    months = []
    current = from_date.replace(day=1)

    while current <= to_date:
        months.append(current.strftime("%b %Y"))

        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    return months

# def execute(filters=None):

#     filters = frappe._dict(filters or {})

#     columns = [
#         "Customer Name:Data:250",
#         "Monthly Target:Currency:180",
#         "Commission Rate (%):Percent:150",
#         "Actual Sales:Currency:180",
#         "Growth Amount:Currency:180",
#         "Var %:Percent:150",
#         "Incentive:Currency:180",
#     ]

#     data = get_report_data(filters)

#     return columns, data

def execute(filters=None):

    filters = frappe._dict(filters or {})

    months = get_month_list(filters.get("from_date"), filters.get("to_date"))

    columns = [
        "Customer Name:Data:250",
        "Monthly Target:Currency:180",
        "Commission Rate (%):Percent:150"
    ]

    for month in months:
        columns.extend([
            f"{month} Actual:Currency:150",
            f"{month} Growth:Currency:150",
            f"{month} Var %:Percent:130",
            f"{month} Incentive:Currency:150",
        ])

    data = get_report_data(filters, months)

    return columns, data

# ----------------------------------------------------------
# STEP 2 — Fetch Target + Actual
# ----------------------------------------------------------

def get_report_data(filters, months):

    if not filters.get("sales_person"):
        return []

    # 1️⃣ Fetch Customers with Target + Commission
    customers = frappe.db.sql("""
        SELECT
            c.name,
            c.customer_name,
            st.custom_monthly_revenue_target,
            st.commission_rate
        FROM `tabCustomer` c
        INNER JOIN `tabSales Team` st
            ON st.parent = c.name
        WHERE st.sales_person = %(sales_person)s
    """, {
        "sales_person": filters.get("sales_person")
    }, as_dict=True)

    # 2️⃣ Fetch Actual Sales grouped by Month
    actual_sales = frappe.db.sql("""
        SELECT
            si.customer,
            DATE_FORMAT(si.posting_date, '%%b %%Y') as month,
            SUM(si.base_grand_total) as total_actual
        FROM `tabSales Invoice` si
        INNER JOIN `tabSales Team` st
            ON st.parent = si.name
        WHERE
            si.docstatus = 1
            AND st.sales_person = %(sales_person)s
            AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
        GROUP BY si.customer, month
    """, {
        "sales_person": filters.get("sales_person"),
        "from_date": filters.get("from_date"),
        "to_date": filters.get("to_date"),
    }, as_dict=True)

    # Convert actual sales into dictionary
    actual_map = {}
    for row in actual_sales:
        if row.customer not in actual_map:
            actual_map[row.customer] = {}
        actual_map[row.customer][row.month] = float(row.total_actual or 0)

    data = []

    # 🔥 Initialize totals dictionary
    totals = {}
    for month in months:
        totals[month] = {
            "target": 0,
            "actual": 0,
            "growth": 0,
            "incentive": 0
        }
    total_target = 0

    # 3️⃣ Build Customer Rows
    for row in customers:

        target = float(row.custom_monthly_revenue_target or 0)
        total_target += target

        commission_raw = row.commission_rate or 0
        if isinstance(commission_raw, str):
            commission_raw = commission_raw.replace("%", "").strip()
        commission = float(commission_raw)

        customer_row = [row.customer_name,target,commission]

        for month in months:

            actual = float(actual_map.get(row.name, {}).get(month, 0))
            growth = actual - target

            if target:
                var_percent = (growth / target) * 100
            else:
                var_percent = 0

            # if actual > target:
            #     incentive = growth * (commission / 100)
            # else:
            #     incentive = 0

            incentive = growth * (commission / 100)

            # 🔥 Accumulate totals
            totals[month]["actual"] += actual
            totals[month]["growth"] += growth
            totals[month]["incentive"] += incentive

            customer_row.extend([
                actual,
                growth,
                var_percent,
                incentive
            ])

        data.append(customer_row)

    # 🔥 Build Grand Total Row
    total_row = ["Grand Total", total_target,""]

    for month in months:

        month_total = totals[month]

        actual_total = month_total["actual"]
        growth_total = month_total["growth"]
        incentive_total = month_total["incentive"]

        if total_target:
            var_total = (growth_total / total_target) * 100
        else:
            var_total = 0

        total_row.extend([
            actual_total,
            growth_total,
            var_total,
            incentive_total
        ])
    if data:
        data.append(total_row)

    return data

