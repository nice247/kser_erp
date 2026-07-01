from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, timedelta

class KserClinicVisit(models.Model):
    _name = 'kser.clinic.visit'
    _description = 'Clinic Patient Visit'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'visit_time desc'

    name = fields.Char(
        string='Visit Ref',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Patient',
        required=True,
        tracking=True,
    )
    receptionist_id = fields.Many2one(
        'res.users',
        string='Receptionist',
        required=True,
        default=lambda self: self.env.user,
        readonly=True,
    )
    doctor_id = fields.Many2one(
        'res.users',
        string='Assigned Doctor',
        required=True,
        domain=lambda self: [('groups_id', 'in', [
            self.env.ref('kser_erp.group_doctor').id,
            self.env.ref('kser_erp.group_clinic_manager').id
        ])],
        tracking=True,
    )
    visit_date = fields.Date(
        string='Visit Date',
        required=True,
        default=lambda self: self._get_default_visit_date(),
        readonly=True,
    )
    visit_time = fields.Datetime(
        string='Check-in Time',
        required=True,
        default=fields.Datetime.now,
        readonly=True,
    )
    state = fields.Selection([
        ('waiting', 'في الانتظار'),
        ('consultation', 'قيد الفحص'),
        ('done', 'اكتملت'),
        ('cancelled', 'ملغاة'),
    ], string='Status', default='waiting', tracking=True)

    prescription_ids = fields.One2many(
        'kser.prescription',
        'visit_id',
        string='Prescriptions',
    )
    followup_ids = fields.One2many(
        'kser.child.followup',
        'visit_id',
        string='Malnutrition Followups',
    )

    @api.model
    def _get_default_visit_date(self):
        now_local = fields.Datetime.context_timestamp(self, datetime.now())
        if now_local.hour < 2:
            return (now_local - timedelta(days=1)).date()
        return now_local.date()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('kser.clinic.visit') or _('New')
        return super().create(vals_list)

    def action_set_consultation(self):
        self.write({'state': 'consultation'})

    def action_set_done(self):
        self.write({'state': 'done'})

    def action_set_cancelled(self):
        self.write({'state': 'cancelled'})

    @api.model
    def action_view_today_queue(self):
        clinic_date = self._get_default_visit_date()
        return {
            'name': _('طابور العيادة اليومي'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.clinic.visit',
            'view_mode': 'list,form',
            'domain': [('visit_date', '=', clinic_date)],
            'context': {'default_visit_date': clinic_date},
        }
