from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    volunteer_id = fields.Many2one(
        'res.partner',
        string='Volunteer',
        domain=[('category_tag', '!=', False)], # Will filter by volunteer category in action context or generic classification tag
        tracking=True,
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Distribution Order (Picking)',
        tracking=True,
    )
    completion_rate = fields.Float(
        string='Completion Rate',
        tracking=True,
    )
    evaluation_notes = fields.Text(
        string='Evaluation Notes',
        tracking=True,
    )

    @api.constrains('completion_rate')
    def _check_completion_rate(self):
        for rec in self:
            if rec.completion_rate and not (0 <= rec.completion_rate <= 100):
                raise ValidationError(_('Completion rate must be between 0 and 100!'))
