from odoo import models, fields, api


class KserPerformanceReport(models.AbstractModel):
    _name = 'report.kser_erp.report_performance_template'
    _description = 'Room Performance & Aid Volume Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        date_from = data.get('date_from', fields.Date.today().replace(month=1, day=1))
        date_to = data.get('date_to', fields.Date.today())

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        moves = self.env['stock.move'].search([
            ('state', '=', 'done'),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            '|',
            ('location_dest_id.usage', '=', 'customer'),
            ('picking_id.picking_type_id.code', '=', 'outgoing'),
        ])
        distribution_lines = []
        unique_beneficiary_counts = {}

        # 1. First pass to calculate unique beneficiaries and their medication status
        for move in moves:
            picking = move.picking_id
            b = move.beneficiary_id
            if not b and picking and picking.partner_id:
                b = self.env['kser.beneficiary'].search([('partner_id', '=', picking.partner_id.id)], limit=1)
            if not b:
                continue
            is_med = move.product_id.is_therapeutic
            if b.id not in unique_beneficiary_counts:
                unique_beneficiary_counts[b.id] = {
                    'family_size': b.family_size or 1,
                    'only_medicine': is_med
                }
            else:
                if not is_med:
                    unique_beneficiary_counts[b.id]['only_medicine'] = False

        # 2. Build distribution lines
        for move in moves:
            picking = move.picking_id
            categ_name = move.product_id.categ_id.name or ''

            if 'أدوية' in categ_name or 'دواء' in categ_name or 'Medicine' in categ_name:
                item_category = 'Medicines'
            elif 'غذائية' in categ_name or 'طعام' in categ_name or 'غذاء' in categ_name or 'Food' in categ_name:
                item_category = 'Foodstuffs'
            else:
                item_category = categ_name

            # Calculate count for this specific move
            b = move.beneficiary_id
            if not b and picking and picking.partner_id:
                b = self.env['kser.beneficiary'].search([('partner_id', '=', picking.partner_id.id)], limit=1)

            beneficiary_count = 0
            if b:
                if move.product_id.is_therapeutic:
                    beneficiary_count = 1
                else:
                    beneficiary_count = b.family_size or 1

            distribution_lines.append({
                'order_name': picking.name if picking else '-',
                'date': move.date.date() if move.date else False,
                'campaign_name': picking.project_id.name if picking and picking.project_id else '-',
                'item_category': item_category,
                'product_name': move.product_id.name,
                'quantity': move.product_uom_qty,
                'uom': move.product_uom.name if move.product_uom else '-',
                'beneficiary_name': b.partner_id.name if b else '-',
                'beneficiary_count': beneficiary_count,
                'distribution_type': dict(
                    picking._fields['distribution_type'].selection
                ).get(picking.distribution_type, '-') if picking and picking.distribution_type else '-',
            })

        distribution_lines.sort(key=lambda x: x.get('date') or fields.Date.today())

        # 3. Calculate total beneficiaries sum based on unique counts to prevent double counting
        total_beneficiaries_sum = 0
        for b_id, info in unique_beneficiary_counts.items():
            if info['only_medicine']:
                total_beneficiaries_sum += 1
            else:
                total_beneficiaries_sum += info['family_size']

        # 4. Populate stats table
        stats = {
            'needy': {'male': 0, 'female': 0, 'total': 0, 'pct': 0.0},
            'patients': {'male': 0, 'female': 0, 'total': 0, 'pct': 0.0},
            'elderly': {'male': 0, 'female': 0, 'total': 0, 'pct': 0.0},
            'orphans': {'male': 0, 'female': 0, 'total': 0, 'pct': 0.0},
            'others': {'male': 0, 'female': 0, 'total': 0, 'pct': 0.0},
        }

        # Query clinic visits in this period to include visited beneficiaries under patients
        visited_beneficiary_ids = set()
        if date_from and date_to:
            visits = self.env['kser.clinic.visit'].search([
                ('visit_date', '>=', date_from),
                ('visit_date', '<=', date_to),
                ('state', '!=', 'cancelled'),
            ])
            visited_beneficiary_ids = set(visits.mapped('beneficiary_id.id'))

        today = fields.Date.today()
        for b_id, info in unique_beneficiary_counts.items():
            b = self.env['kser.beneficiary'].browse(b_id)
            gender = b.gender if b.gender in ['male', 'female'] else 'male'
            
            # Calculate age
            age = 0
            if b.birthdate:
                age = today.year - b.birthdate.year - ((today.month, today.day) < (b.birthdate.month, b.birthdate.day))
            
            # Classify
            if b.is_child or (b.birthdate and age < 18):
                cat = 'orphans'
            elif b.birthdate and age >= 60:
                cat = 'elderly'
            elif b.marital_status == 'widowed' and gender == 'female':
                cat = 'needy'
            elif b.health_conditions or b.is_disabled or (b.id in visited_beneficiary_ids):
                cat = 'patients'
            else:
                cat = 'others'
                
            count_to_add = 1 if info['only_medicine'] else info['family_size']
            stats[cat][gender] += count_to_add
            stats[cat]['total'] += count_to_add

        if total_beneficiaries_sum > 0:
            for cat in stats:
                stats[cat]['pct'] = (stats[cat]['total'] / total_beneficiaries_sum) * 100.0

        return {
            'doc_ids': docids,
            'doc_model': 'stock.move',
            'company': self.env.company,
            'date_from': date_from,
            'date_to': date_to,
            'distribution_lines': distribution_lines,
            'total_distributions': len(distribution_lines),
            'total_beneficiaries': total_beneficiaries_sum,
            'total_quantity': sum(line['quantity'] for line in distribution_lines),
            'stats': stats,
            'notes': data.get('notes', ''),
        }
