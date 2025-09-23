import frappe
from frappe.utils import today

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
        content = {"currency": currency}

        success, response = make_post(
            interfaceCode=interfaceCode,
            content=content,
            company_name=company_name
        )

        if not success:
            frappe.log_error(response, "EFRIS Exchange Rate Fetch Failed")

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

        return {"currency": currency, "rate": rate}

    except Exception as e:
        frappe.log_error(f"EFRIS exchange rate error: {e}", "yana_efris.get_exchange_rate")
        # frappe.throw(f"EFRIS exchange rate call failed: {e}")
