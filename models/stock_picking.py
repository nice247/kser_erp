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
        index=True,
    )
    ai_suggestion = fields.Boolean(
        string='اقتراح آلي؟',
        default=False,
        index=True,
    )
