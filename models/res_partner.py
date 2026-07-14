from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _sql_constraints = [
        ('kser_national_id_unique', 'UNIQUE(national_id_number)',
         'الرقم الوطني هذا مسجل بالفعل لمتطوع آخر!'),
    ]

    category_tag = fields.Many2one(
        'res.partner.category',
        string='Contact Category',
        index=True,
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='Field Supervisor',
        domain=lambda self: [('groups_id', 'in', [self.env.ref('kser_erp.group_field_supervisor', raise_if_not_found=False).id])] if self.env.ref('kser_erp.group_field_supervisor', raise_if_not_found=False) else [],
        index=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
    )

    is_volunteer = fields.Boolean(
        compute='_compute_role_booleans',
        store=True,
    )
    is_donor = fields.Boolean(
        compute='_compute_role_booleans',
        store=True,
    )
    is_beneficiary = fields.Boolean(
        compute='_compute_role_booleans',
        store=True,
    )
    is_clinic_only = fields.Boolean(
        string='Clinic Only',
        compute='_compute_is_clinic_only',
        store=True,
    )

    @api.depends('is_beneficiary', 'national_id_number', 'national_id_image')
    def _compute_is_clinic_only(self):
        for rec in self:
            if rec.is_beneficiary:
                rec.is_clinic_only = not rec.national_id_number or not rec.national_id_image
            else:
                rec.is_clinic_only = False

    @api.depends('category_tag')
    def _compute_role_booleans(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        donor_tag = self.env.ref('kser_erp.partner_category_donor', raise_if_not_found=False)
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
        for rec in self:
            rec.is_volunteer = (rec.category_tag == volunteer_tag) if volunteer_tag else False
            rec.is_donor = (rec.category_tag == donor_tag) if donor_tag else False
            rec.is_beneficiary = (rec.category_tag == beneficiary_tag) if beneficiary_tag else False
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
    )

    @api.model
    def normalize_national_id(self, id_str):
        if not id_str:
            return ''
        eastern_to_western = {
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9',
            '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4',
            '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9',
        }
        normalized = ''.join(eastern_to_western.get(c, c) for c in id_str)
        return normalized.strip()

    @api.constrains('national_id_number', 'national_id_image', 'category_tag')
    def _check_national_id_volunteer(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        for rec in self:
            normalized_id = self.normalize_national_id(rec.national_id_number) if rec.national_id_number else ''
            
            if volunteer_tag and rec.category_tag == volunteer_tag:
                if not rec.national_id_image:
                    raise ValidationError(_("يجب رفع صورة الرقم الوطني للمتطوع!"))
                if not normalized_id or len(normalized_id) != 11 or not normalized_id.isdigit():
                    raise ValidationError(_("يجب أن يتكون الرقم الوطني للمتطوع من 11 خانة رقمية فقط!"))
            
            if normalized_id:
                duplicate = self.with_context(active_test=False).search([
                    ('national_id_number', '=', normalized_id),
                    ('id', '!=', rec.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("عذراً، الرقم الوطني '%s' مسجل بالفعل لجهة الاتصال: '%s'. لا يمكن تكرار الرقم الوطني لمنع التكرار.") % (normalized_id, duplicate.name))

    task_ids = fields.Many2many(
        'project.task',
        string='Volunteer Tasks',
        compute='_compute_task_ids',
    )
    donation_ids = fields.One2many(
        'kser.cash.donation',
        'partner_id',
        string='Donations',
    )

    task_count = fields.Integer(
        compute='_compute_task_count',
        string='Tasks Count',
    )
    donation_count = fields.Integer(
        compute='_compute_donation_count',
        string='Donations Count',
    )

    @api.depends()
    def _compute_task_ids(self):
        for rec in self:
            rec.task_ids = self.env['project.task'].search([('volunteer_ids', 'in', rec.id)])

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids.sudo())

    @api.depends('donation_ids')
    def _compute_donation_count(self):
        for rec in self:
            rec.donation_count = len(rec.donation_ids.sudo())

    def action_view_volunteer_tasks(self):
        self.ensure_one()
        return {
            'name': _('Assigned Tasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('volunteer_ids', 'in', self.id)],
            'context': {'default_volunteer_ids': [(4, self.id)]},
        }

    def action_view_donations(self):
        self.ensure_one()
        return {
            'name': _('Donations'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.cash.donation',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
    whatsapp_number = fields.Char(
        string='WhatsApp Number',
    )
    task_volunteer_ids = fields.One2many(
        'project.task.volunteer',
        'volunteer_id',
        string='مهام التطوع',
    )
    volunteer_completion_rate = fields.Float(
        string='نسبة الإنجاز الكلية',
        compute='_compute_volunteer_completion_rate',
        store=True,
        help='التقييم أو نسبة الإنجاز الكلية للمتطوع الميداني',
    )

    @api.depends('task_volunteer_ids.completion_rate')
    def _compute_volunteer_completion_rate(self):
        for rec in self:
            records = rec.task_volunteer_ids
            if records:
                rates = [r.completion_rate for r in records]
                rec.volunteer_completion_rate = sum(rates) / len(rates)
            else:
                rec.volunteer_completion_rate = 0.0

    incentive_count = fields.Integer(
        compute='_compute_incentive_count',
        string='عدد الحوافز',
    )
    incentive_total = fields.Monetary(
        compute='_compute_incentive_count',
        string='إجمالي الحوافز',
        currency_field='currency_id',
    )
    currency_id = fields.Many2one(
        'res.currency',
        compute='_compute_currency_id',
        string='العملة',
    )

    def _compute_currency_id(self):
        for rec in self:
            rec.currency_id = rec.company_id.currency_id or self.env.company.currency_id

    def _compute_incentive_count(self):
        for rec in self:
            expenses = self.env['kser.cash.expense'].search([
                ('volunteer_id', '=', rec.id),
                ('expense_type', '=', 'volunteer_incentive'),
                ('state', '=', 'posted'),
            ])
            rec.incentive_count = len(expenses)
            rec.incentive_total = sum(e.amount for e in expenses)

    def action_view_incentives(self):
        self.ensure_one()
        return {
            'name': _('Incentives Paid'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.cash.expense',
            'view_mode': 'list,form',
            'domain': [('volunteer_id', '=', self.id), ('expense_type', '=', 'volunteer_incentive')],
            'context': {
                'default_volunteer_id': self.id,
                'default_expense_type': 'volunteer_incentive',
            },
        }

    def action_open_whatsapp(self):
        self.ensure_one()
        if not self.whatsapp_number:
            raise UserError(_("لا يوجد رقم واتساب مسجل لهذا السجل!"))
        num = self.whatsapp_number.strip()
        if num.startswith('0'):
            num = '249' + num[1:]
        num = ''.join(c for c in num if c.isdigit())
        url = f"https://wa.me/{num}"
        return {
            'type': 'ir.actions.act_url',
            'url': url,
            'target': 'new',
        }

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('national_id_number'):
                normalized_id = self.normalize_national_id(vals['national_id_number'])
                vals['national_id_number'] = normalized_id
                
                # التحقق من عدم وجود تكرار قبل الإدخال في قاعدة البيانات
                duplicate = self.with_context(active_test=False).search([
                    ('national_id_number', '=', normalized_id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("عذراً، الرقم الوطني '%s' مسجل بالفعل لجهة الاتصال: '%s'. لا يمكن تكرار الرقم الوطني لمنع التكرار.") % (normalized_id, duplicate.name))
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('national_id_number'):
            normalized_id = self.normalize_national_id(vals['national_id_number'])
            vals['national_id_number'] = normalized_id
            
            # التحقق من عدم وجود تكرار قبل تحديث قاعدة البيانات
            for rec in self:
                duplicate = self.with_context(active_test=False).search([
                    ('national_id_number', '=', normalized_id),
                    ('id', '!=', rec.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("عذراً، الرقم الوطني '%s' مسجل بالفعل لجهة الاتصال: '%s'. لا يمكن تكرار الرقم الوطني لمنع التكرار.") % (normalized_id, duplicate.name))
        return super().write(vals)
