import pandas as pd
import sys
import os
import plotly.express as px
import csv
from operator import itemgetter
import pathlib
import concurrent.futures
import logging
from datetime import datetime
from pyAD import get_ad_user_info  # Ensure pyAD.py is accessible
from getpass import getpass

# -----------------------------
# Argument check and file setup
# -----------------------------
if len(sys.argv) != 2:
    print("Usage: python main3.py <path_to_csv>")
    sys.exit(1)

import_file = sys.argv[1]
file_name = pathlib.Path(import_file).stem

# -----------------------------
# Load and clean input CSV
# -----------------------------
list_of_csv = []
with open(import_file, 'r', encoding='utf8') as read_obj:
    csv_reader = csv.reader(read_obj)
    list_of_csv = list(csv_reader)

for i in range(1, len(list_of_csv)):
    list_of_csv[i][7] = float(list_of_csv[i][7].replace(",", ""))

headers = list_of_csv[0]
data = list_of_csv[1:]
df = pd.DataFrame(data, columns=headers)

try:
    month_str = file_name[-7:]
    df['Month'] = pd.Period(month_str)
except:
    df['Month'] = pd.to_datetime(df['Date']).dt.to_period('M')

month_suffix = str(df['Month'].iloc[0])

# -----------------------------
# Format helper
# -----------------------------
def format_size(kb):
    if kb >= 1_000_000_000:
        return f"{kb / 1_000_000_000:.2f} TB"
    elif kb >= 1_000_000:
        return f"{kb / 1_000_000:.2f} GB"
    elif kb >= 1_000:
        return f"{kb / 1_000:.2f} MB"
    else:
        return f"{kb:.2f} KB"

# -----------------------------
# Cache setup
# -----------------------------
ad_cache_path = pathlib.Path("ad_cache.csv")
try:
    if ad_cache_path.exists() and ad_cache_path.stat().st_size > 0:
        ad_cache_df = pd.read_csv(ad_cache_path, dtype=str).fillna("")
    else:
        raise pd.errors.EmptyDataError
except pd.errors.EmptyDataError:
    ad_cache_df = pd.DataFrame(columns=['User Name', 'first_name', 'last_name', 'job_title', 'organization'])

ad_cache = {}
for _, row in ad_cache_df.iterrows():
    clean_username = row['User Name'].lower().strip()
    ad_cache[clean_username] = {
        'User Name': row['User Name'],
        'first_name': row.get('first_name'),
        'last_name': row.get('last_name'),
        'job_title': row.get('job_title'),
        'organization': row.get('organization')
    }

# -----------------------------
# Logging setup
# -----------------------------
log_filename = f"ad_lookup_log_{month_suffix}.txt"
logging.basicConfig(
    filename=log_filename,
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# -----------------------------
# AD credentials
# -----------------------------
ad_server = input("LDAP server (e.g., ldap://your-ad.local): ").strip()
search_base = input("LDAP search base (e.g., DC=yourdomain,DC=local): ").strip()
bind_username = input("Bind username (e.g., YOURDOMAIN\\username): ").strip()
bind_password = getpass("Bind password: ")

# -----------------------------
# AD Enrichment
# -----------------------------
def enrich_user(username):
    clean_username = username.lower().strip()

    if clean_username in ad_cache:
        logging.info(f"🗃️ Cached: {username}")
        return ad_cache[clean_username]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future = executor.submit(get_ad_user_info, ad_server, search_base, bind_username, bind_password, username)
        try:
            result = future.result(timeout=5)
            if result:
                logging.info(f"✅ AD Lookup: {username}")
                enriched = {
                    'User Name': username,
                    'first_name': result['first_name'],
                    'last_name': result['last_name'],
                    'job_title': result['job_title'],
                    'organization': result['organization']
                }
                ad_cache[clean_username] = enriched
                return enriched
            else:
                logging.warning(f"❌ No result: {username}")
        except concurrent.futures.TimeoutError:
            logging.warning(f"⏱️ Timeout: {username}")
        except Exception as e:
            logging.error(f"❌ Error for {username}: {e}")

    fallback = {
        'User Name': username,
        'first_name': None,
        'last_name': None,
        'job_title': None,
        'organization': None
    }
    ad_cache[clean_username] = fallback
    return fallback

print(f"\n📝 Logging AD lookups to: {log_filename}")
enriched_users = df['User Name'].dropna().unique()
enriched_data = [enrich_user(user) for user in enriched_users]
ad_df = pd.DataFrame(enriched_data)
df = df.merge(ad_df, on='User Name', how='left')

# Save updated cache
updated_cache_df = pd.DataFrame(enriched_data)
updated_cache_df.drop_duplicates(subset=['User Name'], keep='last', inplace=True)
updated_cache_df.to_csv(ad_cache_path, index=False)
print(f"✅ Updated AD cache saved to: {ad_cache_path}")

# -----------------------------
# Stats Computation
# -----------------------------
total_data = df['Total Content Size (KB)'].sum()
rmp_data = df[df['Incident Type'] == 'Removable Storage Protection']['Total Content Size (KB)'].sum()
wp_data = df[df['Incident Type'] == 'Web Protection']['Total Content Size (KB)'].sum()

# File Types
total_by_extension = df.groupby('Evidence File Extension')['Total Content Size (KB)'].sum().reset_index()
total_by_extension = total_by_extension.sort_values(by='Total Content Size (KB)', ascending=False)
unique_by_extension = df['Evidence File Extension'].value_counts().reset_index()
unique_by_extension.columns = ['Evidence File Extension', 'Count']
extension_final = unique_by_extension.merge(total_by_extension, on='Evidence File Extension', how='outer')
extension_final['Total Content Size'] = extension_final['Total Content Size (KB)'].apply(format_size)

# Users
total_by_user = df.groupby('User Name')['Total Content Size (KB)'].sum().reset_index()
total_by_user = total_by_user.sort_values(by='Total Content Size (KB)', ascending=False)
total_by_user['Total Content Size'] = total_by_user['Total Content Size (KB)'].apply(format_size)

# Applications
total_by_application = df.groupby('Source Application Templates')['Total Content Size (KB)'].sum().reset_index()
total_by_application = total_by_application.sort_values(by='Total Content Size (KB)', ascending=False)
total_by_application['Total Content Size'] = total_by_application['Total Content Size (KB)'].apply(format_size)

# USB
usb_df = df[df['Incident Type'] == 'Removable Storage Protection']
total_usb_data = usb_df['Total Content Size (KB)'].sum()
usb_device_stats = usb_df.groupby(['User Name', 'Device Friendly Name '])['USB Serial Number'].nunique().reset_index()
usb_device_stats.columns = ['User Name', 'Device Friendly Name ', 'Unique USB Devices']
unique_usb_serials_rmp = usb_df['USB Serial Number'].nunique()

# Organizations
org_stats = df.groupby('organization')['Total Content Size (KB)'].sum().reset_index()
org_stats = org_stats.sort_values(by='Total Content Size (KB)', ascending=False).head(5)
org_stats['Total Content Size'] = org_stats['Total Content Size (KB)'].apply(format_size)

# Summary
summary_data = {
    'Month': [month_suffix],
    'Total_Data_KB': [total_data],
    'Removable_Storage_KB': [rmp_data],
    'Web_Protection_KB': [wp_data]
}
summary_df = pd.DataFrame(summary_data)

# Output
print(f'\nTotal Data: {total_data}')
print(f'Total Removable Media Protection Data: {rmp_data}')
print(f'Total Web Protection Data: {wp_data}\n')
print("The top 5 file types exfiltrated based on count:")
print(extension_final.sort_values(by='Count', ascending=False).head().to_string(index=False))
print("\nThe top 5 file types exfiltrated based on size:")
print(extension_final.sort_values(by='Total Content Size (KB)', ascending=False).head().to_string(index=False))
print("\nThe top 5 Users based on content size:")
print(total_by_user.head().to_string(index=False))
print(f'Total number of users: {len(total_by_user)}\n')
print("Top Applications:")
print(total_by_application.head().to_string(index=False))
print(f'Total Number of Applications: {len(total_by_application)}\n')
print(f"Total data transferred to USB devices: {format_size(total_usb_data)}\n")
print(usb_device_stats.sort_values(by='Unique USB Devices', ascending=False).head().to_string(index=False))
print(f"\nTotal unique USB Serial Numbers: {unique_usb_serials_rmp}\n")
print("Top 5 Organizations by Total Data Transferred:")
print(org_stats.to_string(index=False))

# File exports
user_stats_path = pathlib.Path(f'user_stats_{month_suffix}.csv')
ext_stats_path = pathlib.Path(f'extension_stats_{month_suffix}.csv')
app_stats_path = pathlib.Path(f'application_stats_{month_suffix}.csv')
org_stats_path = pathlib.Path(f'org_stats_{month_suffix}.csv')
summary_path = pathlib.Path(f'monthly_totals_{month_suffix}.csv')

if not user_stats_path.exists():
    total_by_user.to_csv(user_stats_path, index=False)
if not ext_stats_path.exists():
    extension_final.to_csv(ext_stats_path, index=False)
if not app_stats_path.exists():
    total_by_application.to_csv(app_stats_path, index=False)
if not org_stats_path.exists():
    org_stats.to_csv(org_stats_path, index=False)
if not summary_path.exists():
    summary_df.to_csv(summary_path, index=False)
