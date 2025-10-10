__version__ = "0.0.1"

from yana_efris.api import efris_api
from yana_efris.doctype.e_invoice import e_invoice as yana_einvoice
from uganda_compliance.efris.api_classes import e_invoice
from uganda_compliance.efris.doctype.e_invoice.e_invoice import EInvoice
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error


# Override the method
e_invoice.EInvoiceAPI.generate_irn = efris_api.generate_irn

# Override EInvoice methods (add branch support)
EInvoice.get_einvoice_json = yana_einvoice.get_einvoice_json
EInvoice.get_seller_details_json = yana_einvoice.get_seller_details_json
# Override before_submit of EInvoice
EInvoice.before_submit = yana_einvoice.yana_before_submit


efris_log_info("[YANA EFRIS] Applied overrides for EInvoiceAPI and EInvoice methods")