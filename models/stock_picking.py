from odoo import models, fields


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    distribution_type = fields.Selection(
        [
            ('individual', 'لمستفيد محدد'),
            ('campaign', 'لحملة'),
            ('group', 'لمجموعة'),
        ],
        string='نوع التوزيع',
    )
    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='المستفيد',
        ondelete='set null',
    )
    ai_suggestion = fields.Boolean(
        string='اقتراح آلي؟',
        default=False,
    )
