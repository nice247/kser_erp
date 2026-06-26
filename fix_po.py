import re

with open("i18n/ar.po", "r") as f:
    content = f.read()

lines = content.split('\n')
new_lines = []
is_header = True

for line in lines:
    if line.startswith("msgid") and is_header:
        new_lines.append(line)
        is_header = False
    elif line.startswith("msgid") and not is_header:
        new_lines.append("#. module: kser_erp")
        new_lines.append(line)
    else:
        new_lines.append(line)

with open("i18n/ar.po", "w") as f:
    f.write("\n".join(new_lines))
