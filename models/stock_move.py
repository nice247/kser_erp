from odoo import models, fields


class StockMove(models.Model):
    _inherit = 'stock.move'

    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Beneficiary',
        index=True,
        ondelete='set null',
    )
