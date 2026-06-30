import os

theme_file = '/home/nice/PycharmProjects/Odoo/custom_addons/kser_erp/static/src/scss/kser_theme.scss'
vars_file = '/home/nice/PycharmProjects/Odoo/custom_addons/kser_erp/static/src/scss/kser_variables.scss'

replacements = [
    ("#0c3246", "#113b4a"),
    ("#e62222", "#c92a2a"),
    ("#092433", "#0a252f"),
    ("#0284c7", "#0084b4"),
    ("#0369a1", "#006b94"),
    ("#ef4444", "#c92a2a"),
    # lighter variants for alerts etc if we need, but simple hex is fine
]

def update_file(filepath):
    if not os.path.exists(filepath):
        print(f"File not found: {filepath}")
        return
        
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    for old, new in replacements:
        content = content.replace(old, new)
        # also uppercase versions just in case
        content = content.replace(old.upper(), new)
        
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Updated {filepath}")

update_file(theme_file)
update_file(vars_file)
