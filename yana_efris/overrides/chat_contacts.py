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

@frappe.whitelist()
def get_contacts(user_email):
    companies = get_user_companies(user_email)
    allowed_users = get_users_in_companies(companies)

    contacts_list = frappe.db.sql("""
        SELECT DISTINCT ChatProfile.name AS profile_id,
                        ChatProfile.full_name,
                        Contact.user AS user_id,
                        User.enabled
        FROM `tabClefinCode Chat Profile` AS ChatProfile
        INNER JOIN `tabContact` AS Contact ON Contact.name = ChatProfile.contact
        LEFT OUTER JOIN `tabUser` AS User ON User.name = Contact.user                     
        WHERE (User.enabled = 1 OR User.enabled IS NULL)
        ORDER BY Contact.user DESC
    """, as_dict=True)

    # ✅ filter only contacts of allowed users
    if allowed_users:
        contacts_list = [c for c in contacts_list if c.get("user_id") in allowed_users]

    for contact in contacts_list:
        contact['contact_details'] = frappe.db.sql("""
            SELECT contact_info, type AS contact_type, `default`
            FROM `tabClefinCode Chat Profile Contact Details`
            WHERE parent = %s
        """, (contact['profile_id'],), as_dict=True)

    return {"results": [{"contacts": contacts_list}]}


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
