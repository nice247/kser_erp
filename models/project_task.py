from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class ProjectTask(models.Model):
    _inherit = 'project.task'

    completion_rate = fields.Float(
        string='Completion Rate',
    )
    evaluation_notes = fields.Text(
        string='Evaluation Notes',
    )

    @api.constrains('completion_rate')
    def _check_completion_rate(self):
        for rec in self:
            if rec.completion_rate and not (0 <= rec.completion_rate <= 100):
                raise ValidationError(_('Completion rate must be between 0 and 100!'))
