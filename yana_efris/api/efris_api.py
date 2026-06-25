import frappe
from frappe import _
from frappe.utils import today, getdate
from uganda_compliance.efris.api_classes.e_invoice import EInvoiceAPI
from uganda_compliance.efris.api_classes.efris_api import make_post
from uganda_compliance.efris.utils.utils import efris_log_info, efris_log_error
from collections import defaultdict

import json, base64, gzip
from Crypto.Cipher import AES
import frappe
from uganda_compliance.efris.doctype.e_invoice_request_log.e_invoice_request_log import log_request_to_efris
from frappe.utils import cint
from erpnext.selling.page.point_of_sale.point_of_sale import (
	search_by_term,
	filter_result_items,
	get_conditions,
	get_item_group_condition,
	get_stock_availability,
)
from frappe.query_builder import DocType, functions as fn
from frappe.utils import flt, nowdate
from frappe.utils.nestedset import get_root_of
from erpnext.stock.get_item_details import get_conversion_factor
from frappe.utils.pdf import get_pdf
from datetime import date, timedelta


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
		content = {
			"currency": currency,
		}

		success, response = make_post(
			interfaceCode=interfaceCode,
			content=content,
			company_name=company_name
		)

		if not success:
			frappe.log_error(response, "EFRIS Exchange Rate Fetch Failed")
			frappe.throw(response)

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


		# return {"currency": currency, "rate": rate}
		return response

	except Exception as e:
		frappe.log_error(f"EFRIS exchange rate error: {e}", "yana_efris.get_exchange_rate")
		# frappe.throw(f"EFRIS exchange rate call failed: {e}")

@frappe.whitelist()
def fetch_efris_branches(company_name=None):
	"""
	Simple flow:
	  - call EFRIS T138 (make_post)
	  - for each returned branch, find Company with exact matching company_name or name
		(case-insensitive, trimmed)
	  - set Company.custom_branch_id = branchId via db_set
	Returns: { success: True, mapped: [...], not_found: [...] } or error
	"""
	try:
		# import your make_post helper (adjust path as needed)
		from uganda_compliance.efris.api_classes.efris_api import make_post

		status, response = make_post(interfaceCode="T138", content=None, company_name=company_name)
		if not status:
			frappe.log_error(f"EFRIS T138 failed: {response}", "Yana EFRIS - fetch_efris_branches_and_map")
			return {"success": False, "error": response}

		# normalize response -> list of branch dicts
		if isinstance(response, list):
			items = response
		elif isinstance(response, dict):
			items = response.get("branches") or response.get("data") or []
		else:
			items = []

		mapped = []
		not_found = []

		for b in items:
			branch_id = b.get("branchId") or b.get("branch_id") or ""
			branch_name = (b.get("branchName") or b.get("branch_name") or "").strip()

			if not branch_name:
				# skip nameless entries
				continue

			# Exact match search (case-insensitive). First try company_name, then name.
			# Using filters with "=" does case-sensitive matching in DB, so perform normalized compare in Python.
			# Fetch candidate companies and compare normalized strings to simulate case-insensitive exact match.
			candidates = frappe.get_all("Company", fields=["name", "company_name"])
			matched_company = None
			lower_branch = branch_name.lower()

			for c in candidates:
				comp_name = (c.get("company_name") or c.get("name") or "").strip()
				comp_key_name = (c.get("name") or "").strip()
				if comp_name and comp_name.lower() == lower_branch:
					matched_company = c["name"]
					break
				if comp_key_name and comp_key_name.lower() == lower_branch:
					matched_company = c["name"]
					break

			if matched_company:
				# update Company.custom_branch_id if column exists
				if frappe.db.has_column("Company", "custom_branch_id"):
					try:
						frappe.get_doc("Company", matched_company).db_set("custom_branch_id", branch_id)
					except Exception as e:
						frappe.log_error(f"Failed to db_set custom_branch_id for {matched_company}: {e}",
										 "Yana EFRIS - fetch_efris_branches_and_map")
				else:
					frappe.log_error("Company table missing 'custom_branch_id' column", "Yana EFRIS - fetch_efris_branches_and_map")

				mapped.append({"company": matched_company, "branchName": branch_name, "branchId": branch_id})
			else:
				not_found.append({"branchName": branch_name, "branchId": branch_id})

		return {"success": True, "mapped": mapped, "not_found": not_found}

	except Exception as e:
		frappe.log_error(f"Exception in fetch_efris_branches_and_map: {e}", "Yana EFRIS - fetch_efris_branches_and_map")
		return {"success": False, "error": str(e)}


@frappe.whitelist()
def recover_efris_invoice(sales_invoice_name, fdn):
	try:
		from uganda_compliance.efris.api_classes.efris_api import make_post
		from uganda_compliance.efris.api_classes.e_invoice import EInvoiceAPI
		from frappe.model.rename_doc import rename_doc

		sales_invoice = frappe.get_doc(
			"Sales Invoice",
			sales_invoice_name
		)

		status, response = make_post(
			interfaceCode="T108",
			content={
				"invoiceNo": fdn
			},
			company_name=sales_invoice.company
		)

		frappe.log_error(
			frappe.as_json(response),
			"YANA EFRIS RECOVERY RESPONSE"
		)

		if not status:
			return {
				"success": False,
				"error": response
			}

		seller_reference_no = (
			response.get("sellerDetails", {})
			.get("referenceNo")
		)

		invoice_no = (
			response.get("basicInformation", {})
			.get("invoiceNo")
		)

		if not seller_reference_no:
			return {
				"success": False,
				"error": "Seller Reference Number not found in EFRIS response"
			}

		if not invoice_no:
			return {
				"success": False,
				"error": "FDN Number not found in EFRIS response"
			}

		# ------------------------------------------------
		# Already recovered
		# ------------------------------------------------
		if sales_invoice.name == seller_reference_no:
			return {
				"success": False,
				"error": "This invoice has already been recovered."
			}

		# ------------------------------------------------
		# Validate Buyer TIN
		# ------------------------------------------------
		buyer_tin = (
			response.get("buyerDetails", {})
			.get("buyerTin")
		)

		if buyer_tin and sales_invoice.tax_id:
			if str(buyer_tin).strip() != str(sales_invoice.tax_id).strip():
				return {
					"success": False,
					"error": (
						f"TIN mismatch. "
						f"Invoice TIN={sales_invoice.tax_id}, "
						f"EFRIS TIN={buyer_tin}"
					)
				}

		# ------------------------------------------------
		# Validate Invoice Total
		# ------------------------------------------------
		try:
			efris_total = float(
				response.get("summary", {})
				.get("grossAmount", 0)
			)

			erp_total = float(
				sales_invoice.grand_total or 0
			)

			if abs(erp_total - efris_total) > 0.01:
				return {
					"success": False,
					"error": (
						f"Amount mismatch. "
						f"Invoice Total={erp_total}, "
						f"EFRIS Total={efris_total}"
					)
				}

		except Exception as e:
			return {
				"success": False,
				"error": f"Unable to validate invoice amount: {str(e)}"
			}

		# ------------------------------------------------
		# Rename Sales Invoice
		# ------------------------------------------------
		old_invoice_name = sales_invoice.name

		if old_invoice_name != seller_reference_no:

			existing_invoice = frappe.db.exists(
				"Sales Invoice",
				seller_reference_no
			)

			if existing_invoice:
				return {
					"success": False,
					"error": f"Invoice {seller_reference_no} already exists"
				}

			rename_doc(
				"Sales Invoice",
				old_invoice_name,
				seller_reference_no,
				force=True,
				merge=False
			)

		# ------------------------------------------------
		# Reload renamed invoice
		# ------------------------------------------------
		sales_invoice = frappe.get_doc(
			"Sales Invoice",
			seller_reference_no
		)

		# ------------------------------------------------
		# Create E Invoice
		# ------------------------------------------------
		if not frappe.db.exists(
			"E Invoice",
			seller_reference_no
		):
			einvoice = EInvoiceAPI.create_einvoice(
				seller_reference_no
			)

			EInvoiceAPI.handle_successful_irn_generation(
				einvoice,
				response
			)

			# Reload invoice after successful creation
			sales_invoice = frappe.get_doc(
				"Sales Invoice",
				seller_reference_no
			)

			sales_invoice.db_set(
				"efris_e_invoice",
				einvoice.name,
				update_modified=False
			)

		# ------------------------------------------------
		# Update FDN
		# ------------------------------------------------
		sales_invoice.db_set(
			"efris_irn",
			invoice_no,
			update_modified=False
		)

		# ------------------------------------------------
		# Update Sales Invoice status
		# ------------------------------------------------
		if frappe.db.has_column(
			"Sales Invoice",
			"efris_einvoice_status"
		):
			sales_invoice.db_set(
				"efris_einvoice_status",
				"EFRIS Generated",
				update_modified=False
			)
		
		# if sales_invoice.docstatus == 0:
		# 	sales_invoice.submit()

		frappe.db.commit()

		return {
			"success": True,
			"message": "Invoice recovered successfully",
			"fdn": invoice_no,
			"invoice_name": seller_reference_no
		}

	except Exception as e:
		frappe.log_error(
			frappe.get_traceback(),
			"YANA EFRIS RECOVERY ERROR"
		)

		return {
			"success": False,
			"error": str(e)
		}

from uganda_compliance.efris.api_classes.e_invoice import on_submit_sales_invoice

@frappe.whitelist()	
def send_to_efris(doc):	 
	if isinstance(doc, str):
		doc = json.loads(doc)
	# Convert dict to Frappe Document
	if isinstance(doc, dict):
		doc = frappe.get_doc(doc) 
	on_submit_sales_invoice(doc,'manual_submit')
	efris_log_info(
    	f"YANA DEBUG: Returning new_name={getattr(frappe.flags, 'efris_new_name', None)}"
	)
	return {
		"message": "Sales Invoice sent to EFRIS successfully.",
		"status": "success",
		"new_name": getattr(frappe.flags, "efris_new_name", None)
	}

@staticmethod
def generate_irn(sales_invoice):
	"""
	Entry point (server-side) that builds the EFRIS payload and submits it.
	"""
	efris_log_info("generate_irn called ...")

	from yana_efris.utils.custom_naming import generate_document_series

	# Ensure doc exists
	sales_invoice = EInvoiceAPI.parse_sales_invoice(sales_invoice)
	original_name = sales_invoice.name
	efris_log_info(f"Parsed invoice: {original_name}")

	# ---------------------------------------------------------------
	# Predict SAL reference ONLY for auto-named invoices
	# ---------------------------------------------------------------
	if sales_invoice.custom_document_name:
		# Manual invoice → do NOT generate SAL
		predicted_sal_reference = sales_invoice.name
		efris_log_info(
			f"[YANA DEBUG] Manual invoice detected. Using existing name as referenceNo: {predicted_sal_reference}"
		)
	else:
		# Auto-named invoice → predict SAL
		_temp_doc = frappe.copy_doc(sales_invoice)
		generate_document_series(_temp_doc, "efris")
		predicted_sal_reference = _temp_doc.name
		efris_log_info(
			f"[YANA DEBUG] Auto invoice. Predicted SAL referenceNo: {predicted_sal_reference}"
		)


	# ---------------------------------------------------------------
	# 1️⃣ Submit to EFRIS FIRST — do NOT rename yet!
	# ---------------------------------------------------------------
	einvoice = EInvoiceAPI.create_einvoice(sales_invoice.name)
	einvoice.fetch_invoice_details()

	einvoice_json = einvoice.get_einvoice_json(sales_invoice)

	try:
		einvoice_json["sellerDetails"]["referenceNo"] = predicted_sal_reference
		efris_log_info(f"[YANA DEBUG] Updated referenceNo in payload: {predicted_sal_reference}")
	except Exception as e:
		efris_log_info(f"[YANA ERROR] Failed to override referenceNo: {e}")

	company_name = sales_invoice.company
	efris_log_info(f"[YANA DEBUG] taxDetails JSON: {frappe.as_json(einvoice_json.get('taxDetails'))}")
	efris_log_info(f"[YANA DEBUG] goodsDetails JSON: {frappe.as_json(einvoice_json.get('goodsDetails'))}")
	efris_log_info(f"[YANA DEBUG] summary JSON: {frappe.as_json(einvoice_json.get('summary'))}")

	status, response = make_post(
		interfaceCode="T109",
		content=einvoice_json,
		company_name=company_name,
		reference_doc_type=sales_invoice.doctype,
		reference_document=sales_invoice.name
	)

	# ---------------------------------------------------------------
	# 2️⃣ If API FAILED → do NOT rename, do NOT set efris_invoice=1
	# ---------------------------------------------------------------
	if not status:
		frappe.throw(response, title=_('EFRIS Generation Failed'))

	# ---------------------------------------------------------------
	# 3️⃣ API SUCCESS → Now rename invoice from PFI → SAL series
	# ---------------------------------------------------------------
	try:
		efris_log_info("EFRIS success, converting invoice to SAL series...")

		# Reload latest version
		sales_invoice = frappe.get_doc("Sales Invoice", original_name)

		# Mark as EFRIS invoice
		sales_invoice.efris_invoice = 1

		# Generate new SAL name
		
		# ---------------------------------------------------------------
		# Rename ONLY auto-named invoices
		# ---------------------------------------------------------------
		if not sales_invoice.custom_document_name:
			generate_document_series(sales_invoice, "efris")
			new_name = sales_invoice.name
		else:
			new_name = original_name

		frappe.flags.efris_new_name = new_name

		# Rename in DB
		if original_name != new_name:
			frappe.rename_doc("Sales Invoice", original_name, new_name, force=True)
			efris_log_info(f"Renamed invoice: {original_name} → {new_name}")

			# 🔥 Update EInvoice reference_doc AFTER renaming
			try:
				frappe.rename_doc("E Invoice", einvoice.name, new_name, force=True)
				efris_log_info(f"Renamed EInvoice: {einvoice.name} → {new_name}")
				einvoice = frappe.get_doc("E Invoice", new_name)
				# einvoice.reference_document = new_name
				einvoice.save()
				efris_log_info(f"Updated EInvoice reference_document to {new_name}")
			except Exception as e:
				efris_log_info(f"Failed to update EInvoice reference_document: {e}")

		# Save renamed doc
		sales_invoice = frappe.get_doc("Sales Invoice", new_name)
		sales_invoice.flags.ignore_validate_update_after_submit = True
		sales_invoice.custom_sal_invoice_name = new_name
		sales_invoice.flags.ignore_validate = True
		sales_invoice.flags.ignore_on_update = True
		sales_invoice.flags.ignore_mandatory = True
		sales_invoice.posting_date = frappe.utils.today()
		sales_invoice.posting_time = frappe.utils.nowtime()
		if sales_invoice.due_date == sales_invoice.get_db_value("posting_date"):
			sales_invoice.due_date = frappe.utils.today()
		sales_invoice.save()

	except Exception as e:
		efris_log_info(f"Error renaming invoice after EFRIS success: {e}")
		frappe.throw(f"Invoice renaming failed: {e}")

	# ---------------------------------------------------------------
	# 4️⃣ Continue success workflow
	# ---------------------------------------------------------------
	EInvoiceAPI.handle_successful_irn_generation(einvoice, response)
	efris_log_info(f"EFRIS Generated Successfully. :{einvoice.name}")
	frappe.msgprint(_("EFRIS Generated Successfully."), alert=1)

	return status, response

@staticmethod
def decrypt_aes_ecb(aeskey, ciphertext):

	try:
		# Step 1: Base64 decode
		raw = base64.b64decode(ciphertext)

		data = raw

		# Step 2: If starts with gzip header, decompress
		if data.startswith(b'\x1f\x8b'):
			try:
				data = gzip.decompress(data)
			except Exception as e:
				frappe.log_error(f"❌ GZIP1 failed: {e}", "DEBUG")
				return None

		# Step 3: Try to parse JSON directly
		try:
			text = data.decode("utf-8")
			json.loads(text)  # validate
			return text
		except:
			frappe.log_error("ℹ Not valid JSON yet. Trying AES decrypt...", "DEBUG")

		# Step 4: AES decrypt (ECB, PKCS7)
		cipher = AES.new(aeskey, AES.MODE_ECB)
		decrypted = cipher.decrypt(data)

		padding_length = decrypted[-1]
		decrypted = decrypted[:-padding_length]

		# Step 5: If result is gzip again, decompress
		if decrypted.startswith(b'\x1f\x8b'):
			try:
				decrypted = gzip.decompress(decrypted)
			except Exception as e:
				frappe.log_error(f"❌ GZIP2 failed: {e}", "DEBUG")

		# Step 6: Now decode text
		final_text = decrypted.decode("utf-8")
		return final_text

	except Exception as e:
		frappe.log_error(f"❌ FINAL decrypt error: {e}", "DEBUG")
		raise

@frappe.whitelist()
def query_customer_details(doc, e_company_name, tax_id, ninBrn,accountManager):
	# 1️⃣ Call EFRIS API
	query_customer_details_T119 = {
		"tin": tax_id,
		"ninBrn": ninBrn
	}

	success, response = make_post(
		interfaceCode="T119",
		content=query_customer_details_T119,
		company_name=e_company_name,
	)

	if not success:
		frappe.throw(f"Failed to fetch customer details from EFRIS. Response: {response}")

	# 2️⃣ Extract taxpayer info
	taxpayer = response.get("taxpayer")
	if not taxpayer:
		frappe.throw("EFRIS did not return taxpayer information.")

	# 3️⃣ Choose customer name
	customer_name = taxpayer.get("legalName") or taxpayer.get("businessName")
	if not customer_name:
		frappe.throw("No valid legal/business name found in EFRIS response.")

	# 4️⃣ Optional: double-check if already exists by tax_id
	existing = frappe.db.get_value("Customer", {"tax_id": taxpayer.get("tin")}, "name")
	if existing:
		return {
			"customer_name": existing,
			"message": "Existing customer found."
		}

	# 5️⃣ Create new Customer
	customer = frappe.new_doc("Customer")
	customer.customer_name = customer_name
	customer.customer_type = "Company"
	customer.efris_customer_type = "B2B"  # ✅ Custom field (make sure it exists)
	customer.account_manager = accountManager
	customer.customer_group = "Commercial"

	# 6️⃣ Map optional fields
	if taxpayer.get("tin"):
		customer.tax_id = taxpayer.get("tin")

	if taxpayer.get("address"):
		# NOTE: Customer doctype normally doesn't have primary_address field by default.
		# If you created a custom field, it's fine.
		customer.primary_address = taxpayer.get("address")

	customer.insert(ignore_permissions=True)   # <--- NO contact created here (email/mobile empty)
	frappe.db.commit()

	if taxpayer.get("contactEmail"):
		customer.db_set("email_id", taxpayer.get("contactEmail"))

	if taxpayer.get("contactNumber"):
		customer.db_set("mobile_no", taxpayer.get("contactNumber"))

	# 7️⃣ Save
	# customer.save()
	# frappe.db.commit()

	return {
		"customer_id": customer.name,
		"customer_name": customer.customer_name,
		"message": "New customer created successfully.",
		"taxpayer": taxpayer,
	}


@frappe.whitelist()
def fetch_items_from_efris(pageNo,pageSize,company_name):
	fetch_items_T127 = {
		"pageNo": pageNo,
		"pageSize": pageSize,
	}

	success, response = make_post(
		interfaceCode="T127",
		content=fetch_items_T127,
		company_name=company_name,
	)

	if not success:
		frappe.throw("Failed to fetch items from EFRIS (T127). Check logs and credentials.")
	
	return response

@frappe.whitelist()
def fetch_live_stock_by_goods_code(goods_code, company=None):
	"""
	Fetch item details & live stock from EFRIS using Interface Code T127.
	Stores EFRIS Item ID in Item master for future use.
	"""
	if not goods_code:
		return {"success": False, "message": "Missing goods code."}

	payload = {
		"goodsCode": goods_code,
		"pageNo": "1",
		"pageSize": "10"
	}

	success, response = make_post(
		interfaceCode="T127",
		content=payload,
		company_name=company or frappe.defaults.get_user_default("Company")
	)

	if not success:
		return {"success": False, "message": response}

	# Expecting response.records[0]
	record = None
	if isinstance(response, dict) and response.get("records"):
		record = response["records"][0]
	elif isinstance(response, list) and len(response) > 0:
		record = response[0]

	if not record:
		return {"success": False, "message": "No item found in EFRIS."}

	item_id = record.get("id")
	stock = record.get("stock")

	return {"success": True, "live_stock": stock, "efris_item_id": item_id}

@frappe.whitelist()
def validate_fdn_number(fdn_number, company=None):
	"""
	Validate Invoice FDN Number using EFRIS Interface Code T108.
	Returns RAW EFRIS response (no custom formatting).
	"""

	if not fdn_number:
		return {"error": "FDN Number is required."}

	payload = {
		"invoiceNo": fdn_number
	}

	# Call using same pattern as other functions
	success, response = make_post(
		interfaceCode="T108",
		content=payload,
		company_name=company or frappe.defaults.get_user_default("Company")
	)

	if not success:
		return {"success": False, "message": response}
	
	goods = response.get("goodsDetails", [])
	seller = response.get("sellerDetails", {})
	basic = response.get("basicInformation", {})
	tax_details = response.get("taxDetails", [])
	summary = response.get("summary", {})

	# 2. Check if all items exist in ERPNext
	missing_items = []
	for g in goods:
		item_code = g.get("itemCode")
		if not frappe.db.exists("Item", item_code):
			missing_items.append(item_code)

	if missing_items:
		frappe.throw(f"Items not found in ERPNext: {', '.join(missing_items)}")

	# Return raw EFRIS response exactly as received
	return {
		"seller": seller,
		"basic": basic,
		"goods": goods,
		"tax_details": tax_details,
		"summary": summary
	}


def get_efris_product_code(item_code):
	product_code = frappe.db.get_value("Item", item_code, "item_code")
	if not product_code:
		frappe.throw(f"No EFRIS Product Code found for item: {item_code}")
	return product_code

@frappe.whitelist()
def get_sidebar_items():
	user_roles = set(frappe.get_roles(frappe.session.user))  # Use a set for faster lookups
	
	# Prepare sidebar items for user role "System Manager"
	def get_system_manager_items():
		return [
			{
				"categoryName": _("System Management"), "link": "", "icon": "setting-gear", "items": [
					{"label": _("Workflows"), "link": f"/app/workflow", "icon": "workflow", "items": []},
					{"label": _("Notifications"), "link": f"/app/notification", "icon": "notification", "items": []},
					{"label": _("Client Scripts"), "link": f"/app/client-script", "icon": "small-file", "items": []},
					{"label": _("Property Settings"), "link": f"/app/property-setter", "icon": "shortcut", "items": []},
					{"label": _("System Settings"), "link": f"/app/system-settings", "icon": "tool", "items": []},
					{"label": _("Role Permissions Management"), "link": f"/app/permission-manager", "icon": "permission", "items": []},
				]
			},
			{
				"categoryName": _("Logs"), "link": "", "icon": "list-alt", "items": [
					{"label": _("Activity Logs"), "link": f"/app/activity-log", "icon": "list-alt", "items": []},
					{"label": _("View Logs"), "link": f"/app/view-log", "icon": "list-alt", "items": []},
					{"label": _("Access Logs"), "link": f"/app/access-log", "icon": "list-alt", "items": []},
					{"label": _("Error Logs"), "link": f"/app/error-log", "icon": "list-alt", "items": []},
				]
			},
		]
		
	# Map roles to function references directly
	sidebar_items = {
		"System Manager": get_system_manager_items,
	}
	
	# If the user has the role "System Manager", return the items for that role
	if "System Manager" in user_roles:
		return {"System Manager": sidebar_items["System Manager"]()}
		
	# Find the first matching role (assuming each user has only one role)
	for role in user_roles:
		if role in sidebar_items:
			function = sidebar_items[role]  # Get the function reference
			return {role: function()}  # Call the function directly

	return {}  # Return empty if no matching role is found


@frappe.whitelist()
def get_items(start, page_length, item_group, pos_profile, search_term=""):

	frappe.log_error(f"Custom POS items started working", "Custom POS Items Filter")
	# Get POS Profile data
	# warehouse, hide_unavailable_items, company = frappe.db.get_value(
	#     "POS Profile",
	#     pos_profile,
	#     ["warehouse", "hide_unavailable_items", "company"],
	# )

	warehouse, hide_unavailable_items, company, price_list = frappe.db.get_value(
		"POS Profile",
		pos_profile,
		["warehouse", "hide_unavailable_items", "company", "selling_price_list"],
	)


	if not warehouse:
		frappe.throw("Warehouse is not set in POS Profile.")

	result = []

	# 🔎 Search handling
	if search_term:
		result = search_by_term(search_term, warehouse, price_list) or []
		filter_result_items(result, pos_profile)
		if result:
			return {"items": result}

	if not frappe.db.exists("Item Group", item_group):
		item_group = get_root_of("Item Group")

	condition = get_conditions(search_term)
	condition += get_item_group_condition(pos_profile)

	lft, rgt = frappe.db.get_value("Item Group", item_group, ["lft", "rgt"])

	# 🔥 FORCE warehouse-based filtering ALWAYS (KEY FIX)
	bin_join_selection = """
		INNER JOIN `tabBin` bin
			ON bin.item_code = item.name
			AND bin.warehouse = %(warehouse)s
	"""

	bin_join_condition = ""

	items_data = frappe.db.sql(
		f"""
		SELECT
			item.name AS item_code,
			item.item_name,
			item.description,
			item.stock_uom,
			item.image AS item_image,
			item.is_stock_item,
			item.sales_uom
		FROM
			`tabItem` item
			{bin_join_selection}
		WHERE
			item.disabled = 0
			AND item.has_variants = 0
			AND item.is_sales_item = 1
			AND item.is_fixed_asset = 0
			AND item.item_group IN (
				SELECT name FROM `tabItem Group`
				WHERE lft >= {cint(lft)} AND rgt <= {cint(rgt)}
			)
			AND {condition}
		ORDER BY
			item.name ASC
		LIMIT
			{cint(page_length)} OFFSET {cint(start)}
		""",
		{"warehouse": warehouse},
		as_dict=1,
	)

	if not items_data:
		return {"items": []}

	current_date = frappe.utils.today()

	for item in items_data:

		# item.actual_qty, _ = get_stock_availability(item.item_code, warehouse)
		item.actual_qty, _, is_negative_stock_allowed = get_stock_availability(
			item.item_code, warehouse
		)


		item_prices = frappe.get_all(
			"Item Price",
			fields=[
				"price_list_rate",
				"currency",
				"uom",
				"batch_no",
				"valid_from",
				"valid_upto",
			],
			filters={
				"price_list": price_list,
				"item_code": item.item_code,
				"selling": True,
				"valid_from": ["<=", current_date],
				"valid_upto": ["in", [None, "", current_date]],
			},
			order_by="valid_from desc",
		)

		stock_uom_price = next(
			(d for d in item_prices if d.get("uom") == item.stock_uom), {}
		)

		item_uom = item.stock_uom
		item_uom_price = stock_uom_price

		if item.sales_uom and item.sales_uom != item.stock_uom:
			item_uom = item.sales_uom
			sales_uom_price = next(
				(d for d in item_prices if d.get("uom") == item.sales_uom), {}
			)
			if sales_uom_price:
				item_uom_price = sales_uom_price

		if item_prices and not item_uom_price:
			item_uom = item_prices[0].get("uom")
			item_uom_price = item_prices[0]

		item_conversion_factor = get_conversion_factor(
			item.item_code, item_uom
		).get("conversion_factor")

		if item.stock_uom != item_uom:
			item.actual_qty = item.actual_qty // item_conversion_factor

		if item_uom_price and item_uom != item_uom_price.get("uom"):
			item_uom_price.price_list_rate = (
				item_uom_price.price_list_rate * item_conversion_factor
			)

		result.append(
			{
				**item,
				"price_list_rate": item_uom_price.get("price_list_rate"),
				"currency": item_uom_price.get("currency"),
				"uom": item_uom,
				"batch_no": item_uom_price.get("batch_no"),
			}
		)

	return {"items": result}

@frappe.whitelist()
def get_files_in_folder(folder: str, start: int = 0, page_length: int = 20) -> dict:

	current_user = frappe.session.user

	# Get attachment folder (only if belongs to user)
	attachment_folder = frappe.db.get_value(
		"File",
		{
			"file_url": "Home/Attachments",
			"owner": current_user
		},
		["name", "file_name", "file_url", "is_folder", "modified"],
		as_dict=1,
	)

	# Only fetch files owned by logged-in user
	files = frappe.get_list(
		"File",
		{
			"folder": folder,
			"owner": current_user
		},
		["name", "file_name", "file_url", "is_folder", "modified"],
		start=start,
		page_length=page_length + 1,
	)

	# Insert user’s attachment folder if needed
	if folder == "Home" and attachment_folder and attachment_folder not in files:
		files.insert(0, attachment_folder)

	return {
		"files": files[:page_length],
		"has_more": len(files) > page_length
	}

@frappe.whitelist()
def get_customer_credit_summary(customer, company):

	invoices = frappe.db.sql("""
		SELECT name, outstanding_amount, due_date
		FROM `tabSales Invoice`
		WHERE customer = %s
		AND company = %s
		AND docstatus = 1
		AND outstanding_amount > 0
	""", (customer, company), as_dict=True)

	outstanding = 0
	overdue_count = 0
	oldest_days = 0

	for inv in invoices:
		outstanding += inv.outstanding_amount

		if inv.due_date and getdate(inv.due_date) < getdate(today()):
			overdue_count += 1
			days = (getdate(today()) - getdate(inv.due_date)).days

			if days > oldest_days:
				oldest_days = days

	return {
		"outstanding": outstanding,
		"overdue_count": overdue_count,
		"oldest_days": oldest_days
	}

@frappe.whitelist()
def get_supplier_payable_summary(supplier, company):

	invoices = frappe.db.sql("""
		SELECT outstanding_amount, due_date
		FROM `tabPurchase Invoice`
		WHERE supplier = %s
		AND company = %s
		AND docstatus = 1
		AND outstanding_amount > 0
	""", (supplier, company), as_dict=True)

	outstanding = 0
	overdue_count = 0
	oldest_days = 0

	for inv in invoices:
		outstanding += inv.outstanding_amount

		if inv.due_date and getdate(inv.due_date) < getdate(today()):
			overdue_count += 1

			days = (getdate(today()) - getdate(inv.due_date)).days
			if days > oldest_days:
				oldest_days = days

	return {
		"outstanding": outstanding,
		"overdue_count": overdue_count,
		"oldest_days": oldest_days
	}

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_user_companies(doctype, txt, searchfield, start, page_len, filters):

	companies = frappe.get_list(
		"Company",
		fields=["name"],
		filters={
			searchfield: ["like", f"%{txt}%"]
		},
		start=start,
		page_length=page_len,
		ignore_permissions=False
	)

	# ✅ Convert to tuple format required by Frappe
	return [(c.name,) for c in companies]

ITEM_RESULT_FIELDS = [
	"name as item_code",
	"item_name",
	"description",
	"stock_uom",
	"image",
	"is_stock_item",
	"has_batch_no",
	"has_serial_no",
	"item_group",
	"brand",
	"has_variants",
	"variant_of",
	"custom_company",
	"disabled",
]

def _build_item_base_conditions(pos_profile_doc, item_group=None, exclude_variants=True, exclude_templates=False, hide_unavailable=False, warehouse=None):
	"""Build base SQL conditions for POS item search with hierarchical item group support.

	Returns:
		tuple: (conditions, params, extra_joins)
			- conditions: list of WHERE clause strings
			- params: list of params in SQL order (JOIN params first, then WHERE params)
			- extra_joins: SQL JOIN string to insert before WHERE (empty string if none)
	"""
	conditions = [
		"i.disabled = 0",
		"i.is_sales_item = 1",
	]
	if exclude_variants:
		conditions.append("IFNULL(i.variant_of, '') = ''")
	if exclude_templates:
		conditions.append("i.has_variants = 0")

	where_params = []

	if pos_profile_doc.company:
		conditions.append("IFNULL(i.custom_company, '') IN (%s, '')")
		where_params.append(pos_profile_doc.company)

	if item_group:
		item_groups = _get_item_group_with_descendants(item_group)
		placeholders = ", ".join(["%s"] * len(item_groups))
		conditions.append(f"i.item_group IN ({placeholders})")
		where_params.extend(item_groups)

	extra_joins = ""
	join_params = []

	if hide_unavailable and warehouse:
		warehouses = [warehouse]
		if frappe.db.get_value("Warehouse", warehouse, "is_group"):
			warehouses = frappe.db.get_descendants("Warehouse", warehouse) or [warehouse]

		wh_placeholders = ", ".join(["%s"] * len(warehouses))
		extra_joins = f"LEFT JOIN `tabBin` bin ON bin.item_code = i.name AND bin.warehouse IN ({wh_placeholders})"
		join_params.extend(warehouses)
		conditions.append("(i.is_stock_item = 0 OR i.has_variants = 1 OR bin.actual_qty > 0)")

	# Merge: join params come before WHERE params to match SQL placeholder order
	return conditions, join_params + where_params, extra_joins


def _calculate_bundle_availability_bulk(bundle_codes, warehouse):
	"""
	Calculate Product Bundle availability in bulk with component-based calculation.

	This function determines how many complete bundles can be assembled based on
	available component stock. It uses available_qty (actual - reserved) to prevent
	overselling and supports group warehouses for hierarchical stock tracking.

	Product Bundle Availability Logic:
	=====================================
	A bundle's availability is limited by its MOST CONSTRAINED component.

	Example:
		Bundle: "Laptop Combo"
		Components:
			- Laptop (need 1) → available: 50 units → can make 50 bundles
			- Mouse (need 1) → available: 30 units → can make 30 bundles ← LIMITING
			- Keyboard (need 1) → available: 100 units → can make 100 bundles

		Result: Bundle availability = 30 (limited by Mouse stock)

	Stock Calculation:
	==================
	Uses AVAILABLE quantity (actual_qty - reserved_qty) instead of actual_qty
	to prevent overselling when items are reserved in other pending orders.

	Performance Optimization:
	=========================
	- Single bulk query for all bundle components
	- Single bulk query for all component stock levels
	- Handles multiple bundles simultaneously
	- Supports group warehouses (auto-expands to child warehouses)

	Group Warehouse Support:
	========================
	If warehouse is a group warehouse, automatically includes stock from all
	child warehouses in the calculation. This provides accurate availability
	across multiple storage locations.

	Args:
		bundle_codes (list): List of bundle item codes to check
		warehouse (str): Warehouse name (supports group warehouses)

	Returns:
		dict: Mapping of bundle_code -> available_quantity
			  Example: {"BUNDLE-001": 30, "BUNDLE-002": 15}
			  Returns empty dict if no bundles or warehouse not provided

	Example Usage:
		>>> bundles = ["LAPTOP-COMBO", "DESKTOP-BUNDLE"]
		>>> availability = _calculate_bundle_availability_bulk(bundles, "Stores - WH")
		>>> print(availability)
		{"LAPTOP-COMBO": 30, "DESKTOP-BUNDLE": 15}

	Database Queries:
		1. Fetch all bundle components (1 query for all bundles)
		2. Fetch stock for all components (1 query for all items)
		Total: 2 queries regardless of number of bundles

	Edge Cases:
		- No bundles: Returns {}
		- No warehouse: Returns {}
		- Component with 0 stock: Bundle availability = 0
		- Component not in stock table: Treated as 0 availability
		- Group warehouse with no children: Falls back to warehouse itself
	"""
	# ===========================================================================
	# GUARD CLAUSE: Validate inputs
	# ===========================================================================
	if not bundle_codes or not warehouse:
		return {}

	# ===========================================================================
	# STEP 1: Fetch Bundle Component Definitions
	# ===========================================================================
	# Query all bundle definitions and their components in a single query.
	# This is more efficient than querying each bundle separately.
	#
	# Example Result:
	# [
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "LAPTOP", "required_qty": 1},
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "MOUSE", "required_qty": 1},
	#   {"bundle_code": "LAPTOP-COMBO", "component_code": "KEYBOARD", "required_qty": 1}
	# ]
	pb = DocType("Product Bundle")
	pbi = DocType("Product Bundle Item")
	
	bundle_components = (
		frappe.qb.from_(pb)
		.inner_join(pbi).on(pbi.parent == pb.name)
		.select(
			pb.new_item_code.as_("bundle_code"),
			pbi.item_code.as_("component_code"),
			pbi.qty.as_("required_qty")
		)
		.where(pb.new_item_code.isin(bundle_codes))
		.run(as_dict=True)
	)

	if not bundle_components:
		# No bundle definitions found - items are not configured as bundles
		return {}

	# ===========================================================================
	# STEP 2: Extract Unique Component Codes
	# ===========================================================================
	# Get all unique component item codes needed across all bundles.
	# This allows us to fetch stock for all components in a single query.
	#
	# Example: {"LAPTOP", "MOUSE", "KEYBOARD", "MONITOR", "CABLE"}
	component_codes = list(set(c["component_code"] for c in bundle_components))

	# ===========================================================================
	# STEP 3: Resolve Warehouse Hierarchy (Group Warehouse Support)
	# ===========================================================================
	# If the warehouse is a group warehouse, expand to include all child warehouses.
	# This provides accurate stock availability across multiple storage locations.
	#
	# Example:
	#   Input: "Main Store" (group warehouse)
	#   Output: ["Main Store - A", "Main Store - B", "Main Store - C"]
	warehouses = [warehouse]
	if frappe.db.get_value("Warehouse", warehouse, "is_group"):
		child_warehouses = frappe.db.get_descendants("Warehouse", warehouse)
		# Fallback to original warehouse if no children found
		warehouses = child_warehouses or [warehouse]

	# ===========================================================================
	# STEP 4: Fetch Stock Availability for All Components (Bulk Query)
	# ===========================================================================
	# Query stock for all component items across all warehouses in ONE query.
	# Uses available_qty (actual - reserved) to prevent overselling.
	#
	# Performance: Single query handles all components regardless of count
	# Formula: available_qty = actual_qty - reserved_qty
	#
	# Example Result:
	# [
	#   {"item_code": "LAPTOP", "available_qty": 50.0},
	#   {"item_code": "MOUSE", "available_qty": 30.0},
	#   {"item_code": "KEYBOARD", "available_qty": 100.0}
	# ]
	bin = DocType("Bin")
	
	component_stock = (
		frappe.qb.from_(bin)
		.select(
			bin.item_code,
			fn.Coalesce(fn.Sum(bin.actual_qty - bin.reserved_qty), 0).as_("available_qty")
		)
		.where(bin.item_code.isin(component_codes))
		.where(bin.warehouse.isin(warehouses))
		.groupby(bin.item_code)
		.run(as_dict=True)
	)

	# Build fast lookup map: item_code -> available_qty
	# Components not in map are treated as having 0 stock
	component_stock_map = {row["item_code"]: flt(row["available_qty"]) for row in component_stock}

	# ===========================================================================
	# STEP 5: Calculate Bundle Availability (Limited by Most Constrained Component)
	# ===========================================================================
	# For each bundle, determine how many complete bundles can be made based on
	# component availability. The bundle quantity is limited by whichever
	# component can make the FEWEST bundles.
	#
	# Formula: possible_bundles = floor(available_qty / required_qty)
	# Final: bundle_qty = min(possible_bundles across all components)
	#
	# Example:
	#   LAPTOP-COMBO components:
	#     - LAPTOP (need 1): 50 available → 50 possible bundles
	#     - MOUSE (need 1): 30 available → 30 possible bundles ← LIMITING FACTOR
	#     - KEYBOARD (need 1): 100 available → 100 possible bundles
	#   Result: LAPTOP-COMBO availability = 30 (limited by MOUSE)
	bundle_availability = {}
	for comp in bundle_components:
		bundle_code = comp["bundle_code"]
		available = component_stock_map.get(comp["component_code"], 0)
		required = flt(comp["required_qty"])

		if required > 0:
			# Calculate how many bundles this component can supply
			possible = int(available / required)

			# Update bundle availability with minimum across all components
			if bundle_code not in bundle_availability:
				# First component for this bundle
				bundle_availability[bundle_code] = possible
			else:
				# Subsequent components - take minimum (most constrained)
				bundle_availability[bundle_code] = min(bundle_availability[bundle_code], possible)

	return bundle_availability


@frappe.whitelist()
def get_items(pos_profile, search_term=None, item_group=None, start=0, limit=20, include_variants=0, show_variants_as_items=0):
	"""Get items for POS with stock, price, and tax details"""
	try:
		pos_profile_doc = frappe.get_cached_doc("POS Profile", pos_profile)
		

		# Try to resolve weighted/priced barcodes if barcode_resolver is available
		resolved_barcode_data = None
		effective_search_term = search_term
		if search_term and len(search_term.strip().split()) == 1:
			from pos_next.services.barcode import resolve_barcode
			resolved_barcode_data = resolve_barcode(search_term.strip(), pos_profile)
			if resolved_barcode_data and resolved_barcode_data.get("item_barcode"):
				# Use the extracted item barcode for searching
				effective_search_term = resolved_barcode_data["item_barcode"]

		# FILTERING LOGIC:
		# When show_variants_as_items=1: Variants shown directly in grid, templates excluded
		# When show_variants_as_items=0 (default): Templates shown, variants hidden from browse

		# Build base conditions
		show_variants_mode = int(show_variants_as_items)
		if show_variants_mode:
			exclude_variants = False
			exclude_templates = True
		else:
			exclude_variants = not int(include_variants)
			exclude_templates = False
		hide_unavailable = getattr(pos_profile_doc, "hide_unavailable_items", 0)
		conditions, params, extra_joins = _build_item_base_conditions(
			pos_profile_doc, item_group, exclude_variants=exclude_variants,
			exclude_templates=exclude_templates,
			hide_unavailable=hide_unavailable, warehouse=pos_profile_doc.warehouse,
		)

		# ✅ COMPANY FILTER (CORRECT PLACE)
		company = pos_profile_doc.company

		conditions.append("""
			(COALESCE(i.custom_company, '') = %s OR COALESCE(i.custom_company, '') = '')
		""")
		params.append(company)

		# Build column list with table alias
		item_columns = ",\n\t".join([f"i.{col}" for col in ITEM_RESULT_FIELDS])
		# For GROUP BY, extract just the column name (before " as " if present)
		group_by_columns = ", ".join([
			f"i.{col.split(' as ')[0]}" for col in ITEM_RESULT_FIELDS
		])

		# Add search conditions if search term provided
		if effective_search_term and effective_search_term.strip():
			# Split search term into words for fuzzy matching
			search_words = [word.strip() for word in effective_search_term.split() if word.strip()]

			# Word-order independent: all words must appear somewhere in item fields
			search_text = "CONCAT(COALESCE(i.name, ''), ' ', COALESCE(i.item_name, ''), ' ', COALESCE(i.description, ''))"
			word_conditions = " AND ".join([f"{search_text} LIKE %s"] * len(search_words))

			# Also match if barcode contains the search term
			barcode_condition = "ib.barcode = %s"

			# Combine: match item fields OR match barcode
			conditions.append(f"(({word_conditions}) OR {barcode_condition})")
			params.extend([f"%{word}%" for word in search_words])
			params.append(effective_search_term)  # For barcode matching

			# Relevance scoring with case-insensitive comparison
			# Exact barcode match gets highest priority, use MAX() for grouping
			prefix_pattern = f"{effective_search_term}%"
			relevance = f"""
				MAX(CASE
					WHEN ib.barcode = %s THEN 1500
					WHEN ib.barcode LIKE %s THEN 1200
					WHEN LOWER(i.item_name) = LOWER(%s) THEN 1000
					WHEN LOWER(i.name) = LOWER(%s) THEN 900
					WHEN LOWER(i.item_name) LIKE LOWER(%s) THEN 500
					WHEN LOWER(i.name) LIKE LOWER(%s) THEN 400
					ELSE 100
				END)
			"""
			score_params = [effective_search_term, prefix_pattern, effective_search_term, effective_search_term, prefix_pattern, prefix_pattern]
			order_by = f"{relevance} DESC, i.item_name ASC"
		else:
			# No search term - simple ordering
			score_params = []
			order_by = "i.item_name ASC"

		where_clause = " AND ".join(conditions)

		query = f"""
			SELECT {item_columns},
				GROUP_CONCAT(DISTINCT ib.barcode) as barcode,
				GROUP_CONCAT(DISTINCT ib.uom) as barcode_uoms
			FROM `tabItem` i
			LEFT JOIN `tabItem Barcode` ib ON ib.parent = i.name
			{extra_joins}
			WHERE {where_clause}
			GROUP BY {group_by_columns}
			ORDER BY {order_by}
			LIMIT %s OFFSET %s
		"""

		all_params = params + score_params + [limit, start]
		items = frappe.db.sql(query, tuple(all_params), as_dict=1)

		# Prepare maps for enrichment
		item_codes = [item["item_code"] for item in items]
		conversion_map = defaultdict(dict)  # parent -> {uom: factor}
		uom_map = {}  # parent -> [ {uom, conversion_factor}, ... ]
		uom_prices_map = {}  # item_code -> {uom: price_list_rate}

		# UOM conversions (both list & map for quick lookup)
		if item_codes:
			conversions = frappe.get_all(
				"UOM Conversion Detail",
				filters={"parent": ["in", item_codes]},
				fields=["parent", "uom", "conversion_factor"],
			)
			for row in conversions:
				# build list
				uom_map.setdefault(row.parent, []).append(
					{"uom": row.uom, "conversion_factor": row.conversion_factor}
				)
				# build fast lookup
				if row.uom:
					conversion_map[row.parent][row.uom] = row.conversion_factor

		# UOM-specific prices - batch query ALL prices for all items using Query Builder
		if item_codes:
			ItemPrice = DocType("Item Price")
			prices = (
				frappe.qb.from_(ItemPrice)
				.select(
					ItemPrice.item_code,
					ItemPrice.uom,
					ItemPrice.price_list_rate
				)
				.where(ItemPrice.item_code.isin(item_codes))
				.where(ItemPrice.price_list == pos_profile_doc.selling_price_list)
				.orderby(ItemPrice.item_code)
				.orderby(ItemPrice.uom)
				.run(as_dict=True)
			)
			for price in prices:
				uom_prices_map.setdefault(price["item_code"], {})[price["uom"]] = price["price_list_rate"]

		# Batch query stock for all items at once using Query Builder
		stock_map = {}
		if item_codes and pos_profile_doc.warehouse:
			stock_items = [item["item_code"] for item in items if item.get("is_stock_item")]
			if stock_items:
				Bin = DocType("Bin")
				stocks = (
					frappe.qb.from_(Bin)
					.select(
						Bin.item_code,
						Bin.actual_qty
					)
					.where(Bin.item_code.isin(stock_items))
					.where(Bin.warehouse == pos_profile_doc.warehouse)
					.run(as_dict=True)
				)
				stock_map = {s["item_code"]: s["actual_qty"] for s in stocks}

		# ===================================================================
		# PRODUCT BUNDLE AVAILABILITY: Calculate bundle stock (bulk optimized)
		# ===================================================================
		# Product Bundles are "virtual" items assembled from component items.
		# Unlike regular stock items, bundles don't have direct stock entries.
		# Instead, availability is calculated from component stock levels.
		#
		# Example:
		#   Bundle: "Office Starter Kit"
		#   Components:
		#     - Desk (need 1, have 10) → can make 10 bundles
		#     - Chair (need 2, have 15) → can make 7 bundles ← LIMITING
		#     - Lamp (need 1, have 20) → can make 20 bundles
		#   Result: Bundle availability = 7 (limited by chairs)
		#
		# Performance: Single bulk calculation for ALL bundles (not per-item)
		# This is done BEFORE the item enrichment loop for efficiency.
		bundle_availability_map = {}
		if item_codes and pos_profile_doc.warehouse:
			# Bulk calculate availability for all items (bundles auto-detected)
			bundle_availability_map = _calculate_bundle_availability_bulk(
				item_codes,
				pos_profile_doc.warehouse
			)
		elif item_codes and not pos_profile_doc.warehouse:
			# Warning: Bundles require warehouse for component stock lookup
			# Without warehouse, bundles will show as unavailable (qty = 0)
			has_bundles = frappe.db.exists("Product Bundle", {"new_item_code": ["in", item_codes]})
			if has_bundles:
				frappe.log_error(
					"POS Profile missing warehouse - Product Bundles will show as unavailable",
					"Bundle Availability Warning"
				)

		# Variant attributes (only when variants are included)
		attributes_map = {}
		if not exclude_variants:
			variant_codes = [item["item_code"] for item in items if item.get("variant_of")]
			if variant_codes:
				attributes = frappe.get_all(
					"Item Variant Attribute",
					filters={"parent": ["in", variant_codes]},
					fields=["parent", "attribute", "attribute_value"],
				)
				for attr in attributes:
					attributes_map.setdefault(attr["parent"], {})[attr["attribute"]] = attr["attribute_value"]

		# Enrich items with price, stock, barcode, and UOM data
		for item in items:
			stock_uom = item.get("stock_uom")

			# Use pre-loaded price map instead of per-item queries
			price_row = None
			item_prices = uom_prices_map.get(item["item_code"], {})

			# 1) Try price explicitly for stock UOM (preferred)
			if stock_uom and stock_uom in item_prices:
				price_row = {"price_list_rate": item_prices[stock_uom], "uom": stock_uom}

			# 2) If not found, try any price for the item (and capture its UOM)
			elif item_prices:
				# Get first available price
				first_uom = next(iter(item_prices.keys()))
				price_row = {"price_list_rate": item_prices[first_uom], "uom": first_uom}

			# 3) If still not found and it's a template, derive min variant price
			derived_price = None
			if not price_row and item.get("has_variants"):
				ItemPrice = DocType("Item Price")
				Item = DocType("Item")
				variant_prices = (
					frappe.qb.from_(ItemPrice)
					.inner_join(Item).on(Item.name == ItemPrice.item_code)
					.select(fn.Min(ItemPrice.price_list_rate).as_("min_price"))
					.where(Item.variant_of == item["item_code"])
					.where(ItemPrice.price_list == pos_profile_doc.selling_price_list)
					.where(Item.disabled == 0)
					.run(as_dict=True)
				)
				derived_price = (
					variant_prices[0]["min_price"]
					if variant_prices and variant_prices[0].get("min_price")
					else None
				)

			# Finalize display price & display UOM
			display_rate = 0.0
			display_uom = stock_uom

			if price_row:
				raw_rate = flt(price_row.get("price_list_rate") or 0)
				price_uom = price_row.get("uom") or stock_uom
				if price_uom and stock_uom and price_uom != stock_uom:
					# convert to per-stock-UOM if possible
					cf = flt(conversion_map[item["item_code"]].get(price_uom) or 0)
					if cf:
						display_rate = raw_rate / cf
						display_uom = stock_uom
					else:
						# no conversion available: show as is (price UOM)
						display_rate = raw_rate
						display_uom = price_uom
				else:
					display_rate = raw_rate
					display_uom = stock_uom
			elif derived_price is not None:
				display_rate = flt(derived_price)
				display_uom = stock_uom

			item["rate"] = display_rate
			item["price_list_rate"] = display_rate
			item["uom"] = display_uom
			item["price_uom"] = display_uom
			item["conversion_factor"] = 1
			item["price_list_rate_price_uom"] = display_rate

			# ===================================================================
			# STOCK QUANTITY ASSIGNMENT: Stock Items vs Product Bundles
			# ===================================================================
			# Stock items: Use actual_qty from Bin table (direct stock tracking)
			# Product Bundles: Use calculated availability from component stock
			#
			# Decision Logic:
			#   IF item.is_stock_item == 1:
			#     actual_qty = stock from Bin table (or 0 if not in stock)
			#   ELSE:
			#     actual_qty = bundle availability (or 0 if not a bundle)
			#
			# Example 1 - Stock Item (Laptop):
			#   is_stock_item = 1
			#   actual_qty = 50 (from Bin table)
			#
			# Example 2 - Product Bundle (Office Kit):
			#   is_stock_item = 0 (bundles are not stock items)
			#   actual_qty = 7 (calculated from components)
			#
			# Example 3 - Service Item (Consulting):
			#   is_stock_item = 0
			#   actual_qty = 0 (not a bundle, no stock tracking)
			item["actual_qty"] = (
				stock_map.get(item["item_code"], 0)
				if item.get("is_stock_item")
				else bundle_availability_map.get(item["item_code"], 0)
			)

			# ===================================================================
			# BUNDLE MARKER: Flag items that are Product Bundles
			# ===================================================================
			# Add is_bundle=True flag for frontend to identify bundle items.
			# This allows UI to show bundle-specific indicators and handle
			# bundle logic differently (e.g., show component details on click).
			#
			# Bundle Detection: If item_code exists in bundle_availability_map,
			# it means a Product Bundle definition exists for this item.
			if item["item_code"] in bundle_availability_map:
				item["is_bundle"] = True

			# Add warehouse to item (needed for stock validation)
			item["warehouse"] = pos_profile_doc.warehouse

			# Barcode
			# item["barcode"] = barcode_map.get(item["item_code"], "")

			# Item UOMs (exclude stock UOM to avoid duplicates)
			all_uoms = uom_map.get(item["item_code"], []) or []
			item["item_uoms"] = [u for u in all_uoms if u.get("uom") != stock_uom]

			# UOM-specific prices map for frontend selector
			item["uom_prices"] = uom_prices_map.get(item["item_code"], {})

			# Variant attributes
			if item.get("variant_of") and item["item_code"] in attributes_map:
				item["attributes"] = attributes_map[item["item_code"]]

		# Apply resolved barcode data (weighted/priced) to the first matching item
		if resolved_barcode_data and items:
			from pos_next.services.barcode import compute_resolved_item_data
			resolved_item_data = compute_resolved_item_data(
				resolved_barcode_data,
				item=items[0],
			)
			if resolved_item_data:
				items[0].update(resolved_item_data)

		# Post-filter: hide unavailable bundles
		# The SQL-level filter exempts non-stock items (is_stock_item=0) since they
		# have no Bin rows. Bundles are non-stock items whose availability is computed
		# from component stock. Filter them out here if they have 0 availability.
		if hide_unavailable and bundle_availability_map:
			items = [
				item for item in items
				if not item.get("is_bundle") or item.get("actual_qty", 0) > 0
			]

		return items
	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Get Items Error")
		frappe.throw(_("Error fetching items: {0}").format(str(e)))


@frappe.whitelist()
def download_invoice_pdf(doctype, name, format=None):
    # fallback if not provided
    if not format:
        format = frappe.get_meta(doctype).default_print_format or "Standard"

    html = frappe.get_print(
        doctype,
        name,
        print_format=format
    )

    pdf = get_pdf(html)

    frappe.local.response.filename = f"{name}.pdf"
    frappe.local.response.filecontent = pdf
    frappe.local.response.type = "download"

@frappe.whitelist()
def get_user_company():
    user = frappe.session.user

    company = frappe.db.get_value(
        "User Permission",
        {
            "user": user,
            "allow": "Company",
            "is_default": 1
        },
        "for_value"
    )

    # fallback if no default
    if not company:
        company = frappe.db.get_value(
            "User Permission",
            {
                "user": user,
                "allow": "Company"
            },
            "for_value"
        )

    return company

@frappe.whitelist()
def get_user_company_logo():
    company = get_user_company()

    if not company:
        return None

    return frappe.db.get_value("Company", company, "company_logo")

@frappe.whitelist()
def set_active_company(company):
    # 1. Set user default (DB level)
    frappe.defaults.set_user_default("company", company)

    # 2. Set in session (IMPORTANT)
    frappe.local.session.data["company"] = company

    # 3. Clear cache
    frappe.clear_cache(user=frappe.session.user)

    return {"status": "success"}

@staticmethod
def synchronize_e_invoice(doc):   
	from uganda_compliance.efris.api_classes.e_invoice import EInvoiceAPI     
	if doc.get('efris_einvoice_status') == 'EFRIS Generated':
		efris_log_info('synchronize skipped for EFRIS Generated invoice ')
		return
	if frappe.db.exists('E Invoice', doc.name):
		efris_log_info("found einvoice..")
		einvoice = EInvoiceAPI.get_einvoice(doc.name)
		efris_log_info("before sync ...")
		einvoice.sync_with_sales_invoice()
		einvoice.flags.ignore_permissions = True
		efris_log_info("sync_with_sales_invoice done ..")
		einvoice.save()
		efris_log_info("after save...")

@frappe.whitelist()
def get_weekly_sales():
    companies = get_allowed_companies()
    currency_symbol = get_currency_symbol(companies)

    today = date.today()

    # Current week's Monday
    current_monday = today - timedelta(days=today.weekday())

    # Previous week's Monday
    previous_monday = current_monday - timedelta(days=7)

    days = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    data = []

    for i, day_name in enumerate(days):
        current_day = current_monday + timedelta(days=i)
        previous_day = previous_monday + timedelta(days=i)

        this_week = get_day_sales(current_day, companies)
        last_week = get_day_sales(previous_day, companies)

        growth_amount = this_week - last_week

        if last_week > 0:
            growth_percent = round(
                (growth_amount / last_week) * 100,
                2
            )
        else:
            growth_percent = None

        data.append(
            {
                "day": day_name,
                "this_week": this_week,
                "last_week": last_week,
                "growth_amount": growth_amount,
                "growth_percent": growth_percent,
            }
        )

    return {
        "currency_symbol": currency_symbol,
        "data": data,
    }

def get_allowed_companies():
    """
    Returns companies allowed for the current user.
    If no Company User Permissions exist (e.g. Administrator),
    return all companies.
    """
    companies = frappe.get_all(
        "User Permission",
        filters={
            "user": frappe.session.user,
            "allow": "Company",
        },
        pluck="for_value",
    )

    if not companies:
        companies = frappe.get_all("Company", pluck="name")

    return companies

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

def get_day_sales(posting_date, companies):
    """
    Returns total sales for a given date and list of companies.
    Uses base_grand_total so all invoices are compared in company currency.
    """
    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(base_grand_total), 0)
        FROM `tabSales Invoice`
        WHERE
            docstatus = 1
            AND posting_date = %(posting_date)s
            AND company IN %(companies)s
			AND IFNULL(is_return, 0) = 0
        """,
        {
            "posting_date": posting_date,
            "companies": tuple(companies),
        },
    )

    return float(result[0][0] or 0)

@frappe.whitelist()
def get_monthly_sales():
    companies = get_allowed_companies()
    currency_symbol = get_currency_symbol(companies)

    current_year = date.today().year
    last_year = current_year - 1

    months = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]

    data = []

    current_month = date.today().month

    for month_number, month_name in enumerate(months, start=1):

        if month_number > current_month:
            break

        this_year = get_month_sales(
            year=current_year,
            month=month_number,
            companies=companies,
        )

        previous_year = get_month_sales(
            year=last_year,
            month=month_number,
            companies=companies,
        )

        growth_amount = this_year - previous_year

        if previous_year > 0:
            growth_percent = round(
                (growth_amount / previous_year) * 100,
                2,
            )
        else:
            growth_percent = None

        data.append(
            {
                "month": month_name,
                "this_year": this_year,
                "last_year": previous_year,
                "growth_amount": growth_amount,
                "growth_percent": growth_percent,
            }
        )

    return {
        "currency_symbol": currency_symbol,
        "data": data,
    }
	
def get_month_sales(year, month, companies):
    result = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(base_grand_total), 0)
        FROM `tabSales Invoice`
        WHERE
            docstatus = 1
            AND YEAR(posting_date) = %(year)s
            AND MONTH(posting_date) = %(month)s
            AND company IN %(companies)s
            AND IFNULL(is_return, 0) = 0
        """,
        {
            "year": year,
            "month": month,
            "companies": tuple(companies),
        },
    )

    return float(result[0][0] or 0)