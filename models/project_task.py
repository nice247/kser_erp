from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectTask(models.Model):
    _inherit = 'project.task'

    project_id = fields.Many2one(
        'project.project',
        string='Project / Campaign',
    )
    volunteer_id = fields.Many2one(
        'res.partner',
        string='Volunteer',
        domain=lambda self: self._get_volunteer_domain(),
        tracking=True,
    )

    def _get_volunteer_domain(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        domain = [('category_tag', '=', volunteer_tag.id)] if volunteer_tag else []
        if self.env.user.has_group('kser_erp.group_field_supervisor') and not self.env.user.has_group('kser_erp.group_admin_supervisor') and not self.env.user.has_group('kser_erp.group_system_admin'):
            domain.append(('supervisor_id', '=', self.env.user.id))
        return domain
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
