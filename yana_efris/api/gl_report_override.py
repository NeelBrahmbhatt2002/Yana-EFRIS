
import erpnext.accounts.report.general_ledger.general_ledger as gl


def get_data_with_opening_closing(
    filters, account_details, accounting_dimensions, gl_entries
):
    data = []
    totals_dict = gl.get_totals_dict()

    gl.set_bill_no(gl_entries)

    gle_map = gl.initialize_gle_map(
        gl_entries, filters, totals_dict
    )

    totals, entries = gl.get_accountwise_gle(
        filters,
        accounting_dimensions,
        gl_entries,
        gle_map,
        totals_dict,
    )

    # Opening for filtered account
    data.append(totals.opening)

    if not filters.get("categorize_by"):
        all_entries = []

        for acc_dict in gle_map.values():
            all_entries.extend(acc_dict.entries)

        data += all_entries

    elif filters.get("categorize_by") != "Categorize by Voucher (Consolidated)":
        for _acc, acc_dict in gle_map.items():

            if acc_dict.entries:

                # Opening separator
                data.append({
                    "debit_in_transaction_currency": None,
                    "credit_in_transaction_currency": None,
                })

                # Opening
                if (
                    not filters.get("categorize_by")
                    and not filters.get("voucher_no")
                ) or (
                    filters.get("categorize_by")
                    and filters.get("categorize_by") != "Categorize by Voucher"
                ):
                    data.append(acc_dict.totals.opening)

                # GL Entries
                data += acc_dict.entries

                # Total row intentionally removed

                # Closing
                if (
                    not filters.get("categorize_by")
                    and not filters.get("voucher_no")
                ) or (
                    filters.get("categorize_by")
                    and filters.get("categorize_by") != "Categorize by Voucher"
                ):
                    data.append(acc_dict.totals.closing)

        data.append({
            "debit_in_transaction_currency": None,
            "credit_in_transaction_currency": None,
        })

    else:
        data += entries

    # Overall Total row intentionally removed

    # Closing
    data.append(totals.closing)

    return data

