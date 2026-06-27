from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    project_id = fields.Many2one(
        'project.project',
        string='Campaign (Project)',
        index=True,
        tracking=True,
    )
    distribution_type = fields.Selection(
        [
            ('individual', 'Specific Beneficiary'),
            ('campaign', 'Campaign'),
            ('group', 'Group'),
        ],
        string='Distribution Type',
        index=True,
    )
    ai_suggestion = fields.Boolean(
        string='AI Suggestion?',
        default=False,
        index=True,
    )

    def button_validate(self):
        for rec in self:
            if rec.project_id and rec.project_id.state != 'approved':
                raise UserError(_("Cannot validate transfer. The campaign '%s' budget is not approved!") % rec.project_id.name)
        return super().button_validate()
