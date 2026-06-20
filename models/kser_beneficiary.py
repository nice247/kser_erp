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
            ('divorced', 'مطلق'),
            ('widowed', 'أرمل'),
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
    district = fields.Char(
        string='منطقة السكن',
        size=100,
        required=True,
    )
    registration_date = fields.Date(
        string='تاريخ التسجيل',
        required=True,
        default=fields.Date.context_today,
    )
    is_verified = fields.Boolean(
        string='تم الاعتماد؟',
        default=False,
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='ثقة OCR',
    )
    priority_level = fields.Selection(
        [
            ('urgent', 'عاجل'),
            ('medium', 'متوسط'),
            ('normal', 'طبيعي'),
        ],
        string='مستوى الأولوية',
    )
    priority_score = fields.Integer(
        string='درجة الأولوية',
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='رب الأسرة',
        ondelete='set null',
    )
    registered_by = fields.Many2one(
        'res.users',
        string='المسجل بواسطة',
        default=lambda self: self.env.uid,
    )

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

    @api.constrains('priority_score')
    def _check_priority_score(self):
        for rec in self:
            if rec.priority_score and not (0 <= rec.priority_score <= 100):
                raise ValidationError('درجة الأولوية يجب أن تكون بين 0 و 100!')
