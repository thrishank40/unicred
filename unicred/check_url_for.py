import os, re
from app import app

with app.app_context():
    valid_endpoints = list(app.view_functions.keys())

errors = []
for dirpath, dirnames, filenames in os.walk('templates'):
    for f in filenames:
        if f.endswith('.html'):
            path = os.path.join(dirpath, f)
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()
            # find all url_for('something'
            matches = re.findall(r"url_for\(['\"]([^'\"]+)['\"]", content)
            for m in matches:
                # ignore static
                if m == 'static': continue
                # if there is a dot, it might be a blueprint, but we only have app
                if m not in valid_endpoints:
                    errors.append(f"{path}: url_for('{m}') but endpoint '{m}' not found.")

if errors:
    print("URL_FOR ERRORS:")
    for e in errors: print(e)
else:
    print("All url_for endpoints are valid.")
