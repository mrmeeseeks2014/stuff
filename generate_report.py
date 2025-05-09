import os
import pandas as pd
from glob import glob
import plotly.express as px
from jinja2 import Template

input_folder = r'C:\programming\dlp_data\monthly_data'
output_file = 'usb_data_report.html'

# Helper to format KB nicely
def format_size(kb):
    kb = float(kb)
    if kb >= 1_000_000_000:
        return f"{kb / 1_000_000_000:.2f} TB"
    elif kb >= 1_000_000:
        return f"{kb / 1_000_000:.2f} GB"
    elif kb >= 1_000:
        return f"{kb / 1_000:.2f} MB"
    else:
        return f"{kb:.2f} KB"

required_columns = [
    'User Name', 'Incident Type', 'Evidence File Extension',
    'Total Content Size (KB)', 'Source Application Templates',
    'USB Serial Number', 'Device Friendly Name', 'Device Class Name'
]

month_data = {}
summary_user_data = pd.DataFrame()
usb_device_summary = pd.DataFrame()

for file_path in sorted(glob(os.path.join(input_folder, '*.csv'))):
    try:
        df = pd.read_csv(file_path, encoding='utf-8', dtype=str)
        df.columns = [c.strip() for c in df.columns]

        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            print(f"[SKIP] {file_path} missing columns: {missing}")
            continue

        df['Total Content Size (KB)'] = pd.to_numeric(df['Total Content Size (KB)'].str.replace(',', ''), errors='coerce').fillna(0)

        # Derive month name from filename or fallback to date column
        month = os.path.splitext(os.path.basename(file_path))[0][-7:]

        # Totals
        total = df['Total Content Size (KB)'].sum()
        usb_total = df[df['Incident Type'] == 'Removable Storage Protection']['Total Content Size (KB)'].sum()
        web_total = df[df['Incident Type'] == 'Web Protection']['Total Content Size (KB)'].sum()

        # Top 10s
        user_data = df.groupby('User Name')['Total Content Size (KB)'].agg(['sum', 'count']).reset_index()
        user_data.columns = ['User Name', 'Total Size', 'Count']
        ext_data = df.groupby('Evidence File Extension')['Total Content Size (KB)'].agg(['sum', 'count']).reset_index()
        ext_data.columns = ['Extension', 'Total Size', 'Count']
        app_data = df.groupby('Source Application Templates')['Total Content Size (KB)'].agg(['sum', 'count']).reset_index()
        app_data.columns = ['Application', 'Total Size', 'Count']

        month_data[month] = {
            'total': format_size(total),
            'usb_total': format_size(usb_total),
            'web_total': format_size(web_total),
            'top_users_size': user_data.sort_values(by='Total Size', ascending=False).head(10),
            'top_users_count': user_data.sort_values(by='Count', ascending=False).head(10),
            'top_exts_size': ext_data.sort_values(by='Total Size', ascending=False).head(10),
            'top_exts_count': ext_data.sort_values(by='Count', ascending=False).head(10),
            'top_apps_size': app_data.sort_values(by='Total Size', ascending=False).head(10),
            'top_apps_count': app_data.sort_values(by='Count', ascending=False).head(10)
        }

        # Append to summary data
        summary_user_data = pd.concat([summary_user_data, user_data], ignore_index=True)

        usb_df = df[df['USB Serial Number'].notna() & df['USB Serial Number'].str.strip().ne('')]
        if not usb_df.empty:
            usb_info = usb_df[['USB Serial Number', 'Device Friendly Name', 'User Name']].drop_duplicates()
            usb_device_summary = pd.concat([usb_device_summary, usb_info], ignore_index=True)

        print(f"[OK] Processed {file_path}")
    except Exception as e:
        print(f"[ERROR] {file_path}: {e}")

# Summary aggregation
summary_user = summary_user_data.groupby('User Name').agg({'Total Size': 'sum', 'Count': 'sum'}).reset_index()
usb_device_summary = usb_device_summary.drop_duplicates()

# --- HTML Template ---

html_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>DLP Report</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
</head>
<body class="p-4">
    <h1>DLP Monthly Data Report</h1>
    
<ul class="nav nav-tabs" id="tabMenu" role="tablist">
    <li class="nav-item" role="presentation">
        <button class="nav-link active" id="tab-summary" data-bs-toggle="tab" data-bs-target="#content-summary" type="button" role="tab">Summary</button>
    </li>
    {% for month in months %}
    <li class="nav-item" role="presentation">
        <button class="nav-link" id="tab-{{month}}" data-bs-toggle="tab" data-bs-target="#content-{{month}}" type="button" role="tab">{{month}}</button>
    </li>
    {% endfor %}
</ul>


    
<div class="tab-content mt-4">
    <div class="tab-pane fade show active" id="content-summary" role="tabpanel">
        <h3>Summary</h3>
        <h5>Total Data by User</h5>
        {{ summary_user.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Unique USB Devices</h5>
        {{ usb_device_summary.to_html(index=False, classes="table table-striped")|safe }}
    </div>

    {% for month, data in month_data.items() %}
    <div class="tab-pane fade" id="content-{{month}}" role="tabpanel">
        <h3>{{month}}</h3>
        <p><strong>Total Data:</strong> {{data.total}}</p>
        <p><strong>USB Data:</strong> {{data.usb_total}}</p>
        <p><strong>Web Data:</strong> {{data.web_total}}</p>

        <h5>Top 10 Users (by Data Size)</h5>
        {{ data.top_users_size.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Top 10 Users (by Count)</h5>
        {{ data.top_users_count.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Top 10 File Extensions (by Data Size)</h5>
        {{ data.top_exts_size.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Top 10 File Extensions (by Count)</h5>
        {{ data.top_exts_count.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Top 10 Applications (by Data Size)</h5>
        {{ data.top_apps_size.to_html(index=False, classes="table table-striped")|safe }}
        <h5>Top 10 Applications (by Count)</h5>
        {{ data.top_apps_count.to_html(index=False, classes="table table-striped")|safe }}
    </div>
    {% endfor %}
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

# Render and save
template = Template(html_template)

sorted_months = sorted(month_data.keys(), reverse=True)
rendered = template.render(
    months=sorted_months,
    month_data={k: month_data[k] for k in sorted_months},
    summary_user=summary_user,
    usb_device_summary=usb_device_summary
)

with open(output_file, 'w', encoding='utf-8') as f:
    f.write(rendered)

print(f"\n✅ Report saved to {output_file}")
