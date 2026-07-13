cr = env.cr
cr.execute("SELECT * FROM kser_child_followup ORDER BY id ASC")
rows = cr.dictfetchall()
print(f"Found {len(rows)} old follow-up records in the database.")

beneficiary_map = {}
for row in rows:
    ben_id = row['beneficiary_id']
    if ben_id not in beneficiary_map:
        beneficiary_map[ben_id] = []
    beneficiary_map[ben_id].append(row)

for ben_id, ben_rows in beneficiary_map.items():
    main_id = ben_rows[0]['id']
    
    # Create lines for all visits
    for r in ben_rows:
        env['kser.child.followup.line'].create({
            'followup_id': main_id,
            'followup_date': r['followup_date'],
            'weight': r['weight'],
            'height': r['height'],
            'nutrition_status': r['nutrition_status'],
            'next_visit_date': r['next_visit_date'],
            'visit_location': r.get('visit_location') or 'clinic',
            'notes': r.get('notes') or False,
            'measured_by': r.get('measured_by_id') or r.get('create_uid') or env.user.id,
            'visit_id': r.get('visit_id') or False,
        })
    
    # Redirect prescriptions
    dup_ids = [r['id'] for r in ben_rows[1:]]
    if dup_ids:
        env['kser.prescription'].search([('followup_id', 'in', dup_ids)]).write({'followup_id': main_id})
        # Delete duplicate followup records from the database
        if len(dup_ids) == 1:
            cr.execute("DELETE FROM kser_child_followup WHERE id = %s", (dup_ids[0],))
        else:
            cr.execute("DELETE FROM kser_child_followup WHERE id IN %s", (tuple(dup_ids),))
    
    print(f"Migrated duplicate follow-ups to check-up lines for child ID {ben_id}")

env.cr.commit()
print("Data migration completed successfully using raw SQL.")
