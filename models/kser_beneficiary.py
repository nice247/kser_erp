from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class KserBeneficiary(models.Model):
    _name = 'kser.beneficiary'
    _description = 'المستفيدين'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'partner_id'
    _sql_constraints = [
        ('partner_id_unique', 'UNIQUE(partner_id)', 'جهة الاتصال مرتبطة بمستفيد آخر بالفعل!'),
        ('national_id_unique', 'UNIQUE(national_id_number)', 'الرقم الوطني مسجل مسبقاً!'),
    ]

    partner_id = fields.Many2one(
        'res.partner',
        string='جهة الاتصال',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    national_id_number = fields.Char(
        string='الرقم الوطني',
        size=20,
        required=True,
        tracking=True,
    )
    national_id_image = fields.Binary(
        string='صورة الهوية',
        attachment=True,
    )
    profession = fields.Char(
        string='المهنة',
        size=100,
    )
    marital_status = fields.Selection(
        [
            ('single', 'أعزب'),
            ('married', 'متزوج'),
            ('widowed', 'أرمل/ة'),
            ('divorced', 'مطلق/ة'),
        ],
        string='الحالة الاجتماعية',
    )
    family_size = fields.Integer(
        string='عدد أفراد الأسرة',
        required=True,
        default=1,
    )
    health_conditions = fields.Text(
        string='الأمراض المزمنة',
    )
    birthdate = fields.Date(
        string='تاريخ الميلاد',
    )
    district = fields.Char(
        string='منطقة السكن',
        size=100,
        required=True,
        index=True,
    )
    registration_date = fields.Date(
        string='تاريخ التسجيل',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    is_verified = fields.Boolean(
        string='تم الاعتماد؟',
        default=False,
        index=True,
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='ثقة OCR',
    )
    priority_score = fields.Integer(
        string='درجة الأولوية',
        compute='_compute_priority',
        store=True,
    )
    priority_level = fields.Selection(
        [
            ('normal', 'طبيعي'),
            ('medium', 'متوسط'),
            ('urgent', 'عاجل'),
        ],
        string='مستوى الأولوية',
        compute='_compute_priority',
        store=True,
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='رب الأسرة',
        index=True,
        ondelete='set null',
    )
    registered_by = fields.Many2one(
        'res.users',
        string='المسجل بواسطة',
        default=lambda self: self.env.uid,
    )

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
                raise ValidationError('عدد أفراد الأسرة يجب أن يكون أكبر من صفر!')

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError('نسبة ثقة OCR يجب أن تكون بين 0 و 1!')
