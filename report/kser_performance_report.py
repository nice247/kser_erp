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
        ])

        distribution_lines = []
        unique_beneficiaries = set()

        for move in moves:
            picking = move.picking_id
            categ_name = move.product_id.categ_id.name or ''

            if 'أدوية' in categ_name or 'دواء' in categ_name or 'Medicine' in categ_name:
                item_category = 'Medicines'
            elif 'غذائية' in categ_name or 'طعام' in categ_name or 'غذاء' in categ_name or 'Food' in categ_name:
                item_category = 'Foodstuffs'
            else:
                item_category = categ_name

            if move.beneficiary_id:
                unique_beneficiaries.add(move.beneficiary_id.id)

            distribution_lines.append({
                'order_name': picking.name if picking else '-',
                'date': move.date.date() if move.date else False,
                'campaign_name': picking.group_id.name if picking and picking.group_id else '-',
                'item_category': item_category,
                'product_name': move.product_id.name,
                'quantity': move.product_uom_qty,
                'uom': move.product_uom.name if move.product_uom else '-',
                'beneficiary_name': move.beneficiary_id.partner_id.name if move.beneficiary_id else '-',
                'distribution_type': dict(
                    picking._fields['distribution_type'].selection
                ).get(picking.distribution_type, '-') if picking and picking.distribution_type else '-',
            })

        distribution_lines.sort(key=lambda x: x.get('date') or fields.Date.today())

        return {
            'doc_ids': docids,
            'doc_model': 'stock.move',
            'company': self.env.company,
            'date_from': date_from,
            'date_to': date_to,
            'distribution_lines': distribution_lines,
            'total_distributions': len(distribution_lines),
            'total_beneficiaries': len(unique_beneficiaries),
            'total_quantity': sum(line['quantity'] for line in distribution_lines),
        }
