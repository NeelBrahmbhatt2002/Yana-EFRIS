import frappe

def get_user_companies(user_email):
    """Fetch companies assigned via User Permission"""
    return frappe.get_all(
        "User Permission",
        filters={"user": user_email, "allow": "Company"},
        pluck="for_value"
    )

def get_users_in_companies(companies):
    """Fetch users who have permission for these companies"""
    if not companies:
        return []
    return frappe.get_all(
        "User Permission",
        filters={"allow": "Company", "for_value": ["in", companies]},
        pluck="user"
    )

def is_admin_user(user_email):
    return "Yana Support Admin" in frappe.get_roles(user_email)

# @frappe.whitelist()
# def get_contacts(user_email):
#     companies = get_user_companies(user_email)
#     allowed_users = get_users_in_companies(companies)

#     contacts_list = frappe.db.sql("""
#         SELECT DISTINCT ChatProfile.name AS profile_id,
#                         ChatProfile.full_name,
#                         Contact.user AS user_id,
#                         User.enabled
#         FROM `tabClefinCode Chat Profile` AS ChatProfile
#         INNER JOIN `tabContact` AS Contact 
#             ON Contact.name = ChatProfile.contact
#         LEFT OUTER JOIN `tabUser` AS User 
#             ON User.name = Contact.user                     
#         WHERE (User.enabled = 1 OR User.enabled IS NULL)
#           AND Contact.user IS NOT NULL
#           AND Contact.user != %s
#         ORDER BY Contact.user DESC
#     """, (user_email,), as_dict=True)

#     # ✅ filter only contacts of allowed users
#     if allowed_users:
#         contacts_list = [c for c in contacts_list if c.get("user_id") in allowed_users]

#     for contact in contacts_list:
#         contact['contact_details'] = frappe.db.sql("""
#             SELECT contact_info, type AS contact_type, `default`
#             FROM `tabClefinCode Chat Profile Contact Details`
#             WHERE parent = %s
#         """, (contact['profile_id'],), as_dict=True)

#     return {"results": [{"contacts": contacts_list}]}

@frappe.whitelist()
def get_contacts(user_email, limit=20, offset=0, search_text=None):

    search_condition = ""
    search_values = {}

    if search_text:
        search_condition = "AND ChatProfile.full_name LIKE %(search)s"
        search_values["search"] = f"%{search_text}%"

    # 🔹 Fetch all possible contacts (except self)
    contacts_list = frappe.db.sql(f"""
        SELECT DISTINCT
            ChatProfile.name AS profile_id,
            ChatProfile.full_name,
            Contact.user AS user_id,
            User.enabled
        FROM `tabClefinCode Chat Profile` AS ChatProfile
        INNER JOIN `tabContact` AS Contact 
            ON Contact.name = ChatProfile.contact
        LEFT OUTER JOIN `tabUser` AS User 
            ON User.name = Contact.user
        WHERE (User.enabled = 1 OR User.enabled IS NULL)
          AND Contact.user IS NOT NULL
          AND Contact.user != %(user_email)s
        {search_condition}
        ORDER BY Contact.user DESC
    """, {**search_values, "user_email": user_email}, as_dict=True)

    user_is_admin = is_admin_user(user_email)

    # 🔹 Apply company restriction for non-admin users
    if user_is_admin:
        filtered_contacts = contacts_list
    else:
        user_companies = get_user_companies(user_email)
        filtered_contacts = []

        for contact in contacts_list:
            other_user = contact.get("user_id")
            if not other_user:
                continue

            # ✅ Always allow Admin user to appear
            if is_admin_user(other_user):
                filtered_contacts.append(contact)
                continue

            other_companies = get_user_companies(other_user)

            # Check company overlap
            if set(user_companies) & set(other_companies):
                filtered_contacts.append(contact)

    # 🔹 Pagination
    limit = int(limit)
    offset = int(offset)

    page_slice = filtered_contacts[offset: offset + limit]

    # 🔹 Attach contact details (IMPORTANT for frontend)
    for contact in page_slice:
        contact['contact_details'] = frappe.db.sql("""
            SELECT contact_info, 
                   type AS contact_type, 
                   verified, 
                   `default`
            FROM `tabClefinCode Chat Profile Contact Details`
            WHERE parent = %s
        """, (contact['profile_id'],), as_dict=True) or []

    total = len(filtered_contacts)
    next_offset = offset + len(page_slice)
    has_more = next_offset < total

    return {
        "results": [{
            "contacts": page_slice,
            "total": total,
            "has_more": has_more,
            "next_offset": next_offset
        }]
    }

@frappe.whitelist()
def get_contacts_for_new_group(user_email):
    companies = get_user_companies(user_email)
    allowed_users = get_users_in_companies(companies)

    contacts_list = frappe.db.sql("""
        SELECT DISTINCT ChatProfile.name AS profile_id,
                        ChatProfile.full_name,
                        Contact.user AS user_id,
                        User.enabled
        FROM `tabClefinCode Chat Profile` AS ChatProfile
        INNER JOIN `tabClefinCode Chat Profile Contact Details` AS ContactDetails 
            ON ContactDetails.parent = ChatProfile.name
        INNER JOIN `tabContact` AS Contact
            ON Contact.name = ChatProfile.contact
        LEFT OUTER JOIN `tabUser` AS User
            ON User.name = Contact.user                     
        WHERE (User.enabled = 1 OR User.enabled IS NULL)
          AND ContactDetails.contact_info <> %s
          AND ContactDetails.type = 'Chat'
        ORDER BY Contact.user DESC
    """, (user_email,), as_dict=True)

    if allowed_users:
        contacts_list = [c for c in contacts_list if c.get("user_id") in allowed_users]

    for contact in contacts_list:
        contact['contact_details'] = frappe.db.sql("""
            SELECT contact_info, type AS contact_type, `default`
            FROM `tabClefinCode Chat Profile Contact Details`
            WHERE parent = %s AND type = 'Chat'
        """, (contact['profile_id'],), as_dict=True)

    return {"results": [{"contacts": contacts_list}]}
