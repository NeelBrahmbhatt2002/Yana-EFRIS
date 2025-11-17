__version__ = "0.0.1"

from yana_efris.api import efris_api
from uganda_compliance.efris.doctype.e_invoice import e_invoice as original_doceinvoice
from yana_efris.doctype.e_invoice import e_invoice as yana_einvoice
from uganda_compliance.efris.api_classes import e_invoice, encryption_utils
from uganda_compliance.efris.api_classes import efris_api as original_efris_api
from uganda_compliance.efris.doctype.e_invoice.e_invoice import EInvoice
from uganda_compliance.efris.api_classes import stock_in as original_stock_in
from yana_efris.api.efris_api import (
    send_stock_reconciliation as new_send_stock_reconciliation,
    goods_stock_recon_item as new_goods_stock_recon_item
)

# Override generate_irn (already working fine)
e_invoice.EInvoiceAPI.generate_irn = efris_api.generate_irn

# ✅ Replace decrypt AES on module location
encryption_utils.decrypt_aes_ecb = efris_api.decrypt_aes_ecb

# ✅ ALSO replace the local reference used inside efris_api.py
original_efris_api.decrypt_aes_ecb = efris_api.decrypt_aes_ecb

# Override JSON methods (working fine)
EInvoice.get_einvoice_json = yana_einvoice.get_einvoice_json
EInvoice.get_seller_details_json = yana_einvoice.get_seller_details_json
EInvoice.get_tax_details = yana_einvoice.get_tax_details
EInvoice.get_summary = yana_einvoice.get_summary
# original_stock_in.send_stock_reconciliation = new_send_stock_reconciliation
# original_stock_in.goods_stock_recon_item = new_goods_stock_recon_item
# original_doceinvoice.calculate_tax_by_category = yana_einvoice.calculate_tax_by_category
# original_doceinvoice.calculate_additional_discounts = yana_einvoice.calculate_additional_discounts