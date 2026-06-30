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
                raise ValidationError(_('يجب أن تكون نسبة الإنجاز بين 0 و 100!'))

    @api.constrains('volunteer_id')
    def _check_volunteer_assignment(self):
        is_field_supervisor = self.env.user.has_group('kser_erp.group_field_supervisor')
        is_admin = self.env.user.has_group('kser_erp.group_system_admin')
        is_admin_supervisor = self.env.user.has_group('kser_erp.group_admin_supervisor')
        if is_field_supervisor and not (is_admin or is_admin_supervisor):
            for rec in self:
                if rec.volunteer_id:
                    volunteer = rec.volunteer_id
                    if volunteer.supervisor_id != self.env.user and volunteer.create_uid != self.env.user:
                        raise ValidationError(_("لا يمكنك تعيين مهام إلا للمتطوعين التابعين لك!"))
