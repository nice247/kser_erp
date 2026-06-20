from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    completion_rate = fields.Float(
        string='نسبة الإنجاز',
    )
    evaluation_notes = fields.Text(
        string='ملاحظات التقييم',
    )

    @api.constrains('completion_rate')
    def _check_completion_rate(self):
        for rec in self:
            if rec.completion_rate and not (0 <= rec.completion_rate <= 100):
                raise ValidationError('نسبة الإنجاز يجب أن تكون بين 0 و 100!')
