from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class KserBeneficiary(models.Model):
    _name = 'kser.beneficiary'
    _description = 'Beneficiary'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'partner_id'
    _sql_constraints = [
        ('partner_id_unique', 'UNIQUE(partner_id)', 'This contact is already linked to another beneficiary!'),
        ('national_id_unique', 'UNIQUE(national_id_number)', 'This National ID is already registered!'),
    ]

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
        required=True,
        tracking=True,
    )
    phone = fields.Char(
        related='partner_id.phone',
        string='Phone',
        readonly=False,
    )
    mobile = fields.Char(
        related='partner_id.mobile',
        string='Mobile',
        readonly=False,
    )
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
        required=True,
    )
    profession = fields.Char(
        string='Profession',
        size=100,
    )
    marital_status = fields.Selection(
        [
            ('single', 'Single'),
            ('married', 'Married'),
            ('widowed', 'Widowed'),
            ('divorced', 'Divorced'),
        ],
        string='Marital Status',
    )
    family_size = fields.Integer(
        string='Family Size',
        compute='_compute_family_size',
        store=True,
    )
    health_conditions = fields.Text(
        string='Chronic Diseases',
    )
    birthdate = fields.Date(
        string='Birth Date',
    )
    district = fields.Char(
        string='District',
        size=100,
        required=True,
        index=True,
    )
    registration_date = fields.Date(
        string='Registration Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    is_verified = fields.Boolean(
        string='Is Verified?',
        default=False,
        index=True,
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='OCR Confidence',
    )
    priority_score = fields.Integer(
        string='Priority Score',
        compute='_compute_priority',
        store=True,
    )
    priority_level = fields.Selection(
        [
            ('normal', 'Normal'),
            ('medium', 'Medium'),
            ('urgent', 'Urgent'),
        ],
        string='Priority Level',
        compute='_compute_priority',
        store=True,
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='Head of Family',
        index=True,
        ondelete='restrict',
    )
    relationship = fields.Selection(
        [
            ('self', 'رب الأسرة (نفسه)'),
            ('spouse', 'زوج/زوجة'),
            ('child', 'ابن/ابنة'),
            ('parent', 'أب/أم'),
            ('sibling', 'أخ/أخت'),
            ('relative', 'قريب آخر'),
        ],
        string='Relationship to Head of Family',
        default='self',
        required=True,
    )
    member_ids = fields.One2many(
        'kser.beneficiary',
        'head_of_family_id',
        string='Family Members',
        domain=[('relationship', '!=', 'self')],
    )
    registered_by = fields.Many2one(
        'res.users',
        string='Registered By',
        default=lambda self: self.env.uid,
    )

    @api.depends('relationship', 'head_of_family_id', 'member_ids', 'member_ids.relationship')
    def _compute_family_size(self):
        for rec in self:
            if rec.relationship == 'self':
                rec.family_size = 1 + len(rec.member_ids)
            else:
                if rec.head_of_family_id:
                    rec.family_size = rec.head_of_family_id.family_size
                else:
                    rec.family_size = 1

    @api.depends('health_conditions', 'marital_status', 'family_size', 'birthdate')
    def _compute_priority(self):
        today = fields.Date.today()
        for rec in self:
            score = 0

            if rec.health_conditions:
                score += 30

            if rec.marital_status in ('widowed', 'divorced'):
                score += 20

            if rec.family_size > 3:
                score += (rec.family_size - 3) * 5

            if rec.birthdate:
                age = relativedelta(today, rec.birthdate).years
                if age >= 60:
                    score += 15

            rec.priority_score = min(score, 100)

            if rec.priority_score >= 80:
                rec.priority_level = 'urgent'
            elif rec.priority_score >= 50:
                rec.priority_level = 'medium'
            else:
                rec.priority_level = 'normal'

    @api.constrains('family_size')
    def _check_family_size(self):
        for rec in self:
            if rec.family_size < 1:
                raise ValidationError(_('Family size must be greater than zero!'))

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError(_('OCR confidence must be between 0 and 1!'))

    @api.constrains('head_of_family_id', 'relationship')
    def _check_family_relationship(self):
        for rec in self:
            if rec.head_of_family_id and rec.head_of_family_id.id != rec._origin.id:
                if rec.relationship == 'self':
                    raise ValidationError(_("لا يمكن اختيار 'رب الأسرة (نفسه)' إذا كان هناك رب أسرة آخر محدد!"))
            else:
                if rec.relationship != 'self':
                    raise ValidationError(_("يجب أن تكون العلاقة 'رب الأسرة (نفسه)' إذا كان الشخص هو رب الأسرة!"))

    @api.onchange('head_of_family_id')
    def _onchange_head_of_family_id(self):
        if self.head_of_family_id and self.head_of_family_id.id != self._origin.id:
            if self.relationship == 'self':
                self.relationship = 'spouse'
        else:
            self.relationship = 'self'

    @api.onchange('relationship')
    def _onchange_relationship(self):
        if self.relationship == 'self':
            self.head_of_family_id = self._origin.id or False

    move_ids = fields.One2many(
        'stock.move',
        'beneficiary_id',
        string='Relief Received',
    )
    move_count = fields.Integer(
        compute='_compute_move_count',
        string='Relief Count',
    )

    @api.constrains('national_id_number', 'national_id_image')
    def _check_national_id_beneficiary(self):
        for rec in self:
            if not rec.national_id_image:
                raise ValidationError(_("يجب رفع صورة الرقم الوطني للمستفيد!"))
            if not rec.national_id_number or len(rec.national_id_number) != 11 or not rec.national_id_number.isdigit():
                raise ValidationError(_("يجب أن يتكون الرقم الوطني للمستفيد من 11 خانة رقمية فقط!"))

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

    def action_view_moves(self):
        self.ensure_one()
        return {
            'name': _('Relief Received'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('beneficiary_id', '=', self.id)],
            'context': {'default_beneficiary_id': self.id},
        }

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.head_of_family_id:
                rec.head_of_family_id = rec.id
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
        if beneficiary_tag:
            for rec in records:
                if rec.partner_id and rec.partner_id.category_tag != beneficiary_tag:
                    rec.partner_id.category_tag = beneficiary_tag.id
        for rec in records:
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'create',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"Beneficiary registered: National ID {rec.national_id_number}, District: {rec.district}",
            })
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'head_of_family_id' in vals and not vals['head_of_family_id']:
            for rec in self:
                super(KserBeneficiary, rec).write({'head_of_family_id': rec.id})
        if 'partner_id' in vals:
            beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
            if beneficiary_tag:
                for rec in self:
                    if rec.partner_id and rec.partner_id.category_tag != beneficiary_tag:
                        rec.partner_id.category_tag = beneficiary_tag.id
        for rec in self:
            if 'is_verified' in vals and vals['is_verified']:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'approve',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"Beneficiary (National ID: {rec.national_id_number}) was verified",
                })
            elif vals:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'update',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"Beneficiary (National ID: {rec.national_id_number}) was modified: {list(vals.keys())}",
                })
        return res
