user = env['res.users'].search([('login', '=', 'nema')])
print(f"User Name: {user.name}")
print("Groups:")
for g in user.groups_id:
    print(f"- {g.name} (category: {g.category_id.name}, xml_id: {g.get_metadata()[0]['xmlid']})")
