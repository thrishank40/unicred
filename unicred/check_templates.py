import os, re
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

templates = set(re.findall(r"render_template\(['\"]([^'\"]+)", content))
missing = []
for t in templates:
    if not os.path.exists(os.path.join('templates', t)):
        missing.append(t)

if missing:
    print('MISSING TEMPLATES:')
    for m in missing: print(m)
else:
    print('All referenced templates exist.')
