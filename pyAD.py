from ldap3 import Server, Connection, ALL, NTLM
from ldap3.core.exceptions import LDAPException
from getpass import getpass

def get_ad_user_info(ad_server, search_base, bind_username, bind_password, target_username):
    """
    Query Active Directory for a user's first name, last name, job title, and organization.
    """
    try:
        # Connect to the LDAP server
        server = Server(ad_server, get_info=ALL)
        conn = Connection(server, user=bind_username, password=bind_password, authentication=NTLM, auto_bind=True)

        # Perform search
        search_filter = f'(sAMAccountName={target_username})'
        # attributes = ['*']
        attributes = ['givenName', 'sn', 'title', 'physicalDeliveryOfficeName']
        conn.search(search_base, search_filter, attributes=attributes)

        if conn.entries:
            entry = conn.entries[0]
            result = {
                'first_name': str(entry.givenName),
                'last_name': str(entry.sn),
                'job_title': str(entry.title),
                'organization': str(entry.physicalDeliveryOfficeName)
            }
        else:
            result = None

        conn.unbind()
        return result

    except LDAPException as e:
        print(f"LDAP error: {e}")
        return None


if __name__ == '__main__':
    print("🔐 Active Directory Lookup")

    ad_server = input("LDAP server address (e.g., ldap://your-ad-server.local): ").strip()
    search_base = input("LDAP search base (e.g., DC=yourdomain,DC=local): ").strip()
    bind_username = input("Bind username (e.g., YOURDOMAIN\\yourusername): ").strip()
    bind_password = getpass("Bind password (will not be shown): ")
    target_username = input("Target username to look up: ").strip()

    user_info = get_ad_user_info(ad_server, search_base, bind_username, bind_password, target_username)

    if user_info:
        print("\n✅ User Info Found:")
        for key, value in user_info.items():
            print(f"{key.replace('_', ' ').title()}: {value}")
    else:
        print("\n❌ User not found or error occurred.")
