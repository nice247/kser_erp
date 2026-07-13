from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectTaskVolunteer(models.Model):
    _name = 'project.task.volunteer'
    _description = 'Volunteer Assignment on Task'
    _order = 'task_id, id'

    task_id = fields.Many2one(
        'project.task',
        string='المهمة',
        ondelete='cascade',
        required=True,
    )
    volunteer_id = fields.Many2one(
        'res.partner',
        string='المتطوع',
        required=True,
        domain=[('is_volunteer', '=', True)],
    )
    available_volunteer_ids = fields.Many2many(
        'res.partner',
        related='task_id.available_volunteer_ids',
    )
    hours_worked = fields.Float(
        string='ساعات التطوع',
        default=0.0,
    )
    completion_rate = fields.Float(
        string='نسبة الإنجاز %',
        default=0.0,
    )
    incentive_amount = fields.Monetary(
        string='الحافز المستحق',
        currency_field='currency_id',
        default=0.0,
    )
    currency_id = fields.Many2one(
        'res.currency',
        related='task_id.company_id.currency_id',
        string='العملة',
        readonly=True,
    )

    @api.constrains('hours_worked', 'completion_rate', 'incentive_amount')
    def _check_values(self):
        for rec in self:
            if rec.hours_worked < 0:
                raise ValidationError(_('ساعات العمل لا يمكن أن تكون سالبة!'))
            if not (0 <= rec.completion_rate <= 100):
                raise ValidationError(_('يجب أن تكون نسبة الإنجاز بين 0 و 100!'))
            if rec.incentive_amount < 0:
                raise ValidationError(_('الحافز المالي لا يمكن أن يكون سالباً!'))


class ProjectTask(models.Model):
    _inherit = 'project.task'

    project_id = fields.Many2one(
        'project.project',
        string='الحملة',
    )
    task_volunteer_ids = fields.One2many(
        'project.task.volunteer',
        'task_id',
        string='تفاصيل المتطوعين وساعات العمل',
    )
    volunteer_ids = fields.Many2many(
        'res.partner',
        string='Volunteers',
        compute='_compute_volunteer_ids',
        store=True,
    )
    available_volunteer_ids = fields.Many2many(
        'res.partner',
        compute='_compute_available_volunteer_ids',
        store=False,
    )

    @api.depends('task_volunteer_ids.volunteer_id')
    def _compute_volunteer_ids(self):
        for rec in self:
            rec.volunteer_ids = rec.task_volunteer_ids.mapped('volunteer_id')

    @api.depends_context('uid')
    def _compute_available_volunteer_ids(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        base_domain = [('category_tag', '=', volunteer_tag.id)] if volunteer_tag else [('category_tag', '!=', False)]
        
        user = self.env.user
        is_field_supervisor = user.has_group('kser_erp.group_field_supervisor')
        is_admin = user.has_group('kser_erp.group_system_admin')
        is_admin_supervisor = user.has_group('kser_erp.group_admin_supervisor')
        is_data_manager = user.has_group('kser_erp.group_data_manager')

        if is_admin or is_admin_supervisor or is_data_manager:
            allowed_partners = self.env['res.partner'].sudo().search(base_domain)
        elif is_field_supervisor:
            admin_data_users = self.env['res.users'].sudo().search([
                '|',
                ('groups_id', 'in', [self.env.ref('kser_erp.group_admin_supervisor').id]),
                ('groups_id', 'in', [self.env.ref('kser_erp.group_data_manager').id])
            ])
            allowed_uids = admin_data_users.ids + [user.id]
            domain = base_domain + [('create_uid', 'in', allowed_uids)]
            allowed_partners = self.env['res.partner'].sudo().search(domain)
        else:
            allowed_partners = self.env['res.partner'].browse()

        for rec in self:
            rec.available_volunteer_ids = allowed_partners

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

    @api.constrains('volunteer_ids')
    def _check_volunteer_assignment(self):
        is_field_supervisor = self.env.user.has_group('kser_erp.group_field_supervisor')
        is_admin = self.env.user.has_group('kser_erp.group_system_admin')
        is_admin_supervisor = self.env.user.has_group('kser_erp.group_admin_supervisor')
        if is_field_supervisor and not (is_admin or is_admin_supervisor):
            for rec in self:
                for volunteer in rec.volunteer_ids:
                    if volunteer.supervisor_id != self.env.user and volunteer.create_uid != self.env.user:
                        raise ValidationError(_("لا يمكنك تعيين مهام إلا للمتطوعين التابعين لك!"))
