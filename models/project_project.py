from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    budget_amount = fields.Monetary(
        string='Budget Amount',
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('approved', 'Approved'),
            ('done', 'Completed'),
        ],
        string='Budget Status',
        default='draft',
        tracking=True,
        group_expand='_read_group_states',
    )

    picking_ids = fields.One2many(
        'stock.picking',
        'project_id',
        string='Distributions',
    )
    donation_ids = fields.One2many(
        'kser.cash.donation',
        'campaign_id',
        string='Donations',
    )

    picking_count = fields.Integer(
        compute='_compute_picking_count',
        string='Distribution Count',
    )
    donation_count = fields.Integer(
        compute='_compute_donation_count',
        string='Donation Count',
    )

    @api.depends('picking_ids')
    def _compute_picking_count(self):
        for rec in self:
            rec.picking_count = len(rec.picking_ids.sudo())

    @api.depends('donation_ids')
    def _compute_donation_count(self):
        for rec in self:
            rec.donation_count = len(rec.donation_ids.sudo())

    def action_approve_budget(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.state = 'approved'
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'approve',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم اعتماد ميزانية الحملة: {rec.name}، بمبلغ: {rec.budget_amount} {rec.currency_id.name}",
            })

    def action_draft_budget(self):
        for rec in self:
            rec.state = 'draft'
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'update',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تمت إعادة ميزانية الحملة للمسودة: {rec.name}",
            })

    def action_close_campaign(self):
        for rec in self:
            if rec.state != 'approved':
                continue
            rec.state = 'done'
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'update',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم إغلاق الحملة وتأكيد اكتمالها: {rec.name}",
            })

    def action_view_pickings(self):
        self.ensure_one()
        return {
            'name': _('Distributions'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
        }

    def action_view_donations(self):
        self.ensure_one()
        return {
            'name': _('Donations'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.cash.donation',
            'view_mode': 'list,form',
            'domain': [('campaign_id', '=', self.id)],
            'context': {'default_campaign_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        if not (self.env.user.has_group('kser_erp.group_admin_supervisor') or self.env.user.has_group('kser_erp.group_system_admin')):
            raise ValidationError(_("غير مسموح بإنشاء المشاريع / الحملات إلا للمشرف الإداري!"))
        return super().create(vals_list)

    def write(self, vals):
        if not (self.env.user.has_group('kser_erp.group_admin_supervisor') or self.env.user.has_group('kser_erp.group_system_admin')):
            allowed_fields = {'state', 'stage_id', 'active'}
            if not set(vals.keys()).issubset(allowed_fields):
                raise ValidationError(_("المشرف الميداني مسموح له فقط بتحديث حالة المشروع / الحملة عند انتهائه!"))
        return super().write(vals)

    def unlink(self):
        raise ValidationError(_("غير مسموح بحذف المشاريع / الحملات مطلقاً! يمكنكم أرشفتها بدلاً من ذلك."))

    @api.model
    def _read_group_states(self, stages, domain):
        # تجميع وإرجاع الحالات بالترتيب المطلوب: مسودة -> معتمدة -> مكتملة
        return ['draft', 'approved', 'done']
