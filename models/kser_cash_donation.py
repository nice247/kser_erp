from odoo import models, fields, api
from odoo.exceptions import ValidationError


class KserCashDonation(models.Model):
    _name = 'kser.cash.donation'
    _description = 'التبرعات النقدية'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'transaction_number'
    _sql_constraints = [
        ('transaction_number_unique', 'UNIQUE(transaction_number)', 'رقم العملية البنكية مسجل مسبقاً!'),
    ]

    campaign_id = fields.Many2one(
        'project.project',
        string='الحملة المرتبطة',
        ondelete='set null',
        tracking=True,
    )
    amount = fields.Monetary(
        string='المبلغ',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        default=lambda self: self.env.company.currency_id.id,
    )
    transaction_number = fields.Char(
        string='رقم العملية البنكية',
        size=50,
        required=True,
        tracking=True,
    )
    bank_name = fields.Char(
        string='اسم البنك',
        size=20,
        required=True,
    )
    sender_account_number = fields.Char(
        string='رقم حساب المرسل',
        size=30,
        required=True,
    )
    receiver_account_number = fields.Char(
        string='رقم حساب المستلم',
        size=30,
        required=True,
    )
    donation_date = fields.Date(
        string='تاريخ التبرع',
        required=True,
        tracking=True,
    )
    receipt_image = fields.Binary(
        string='صورة الإشعار البنكي',
        attachment=True,
    )
    ocr_status = fields.Selection(
        [
            ('pending', 'قيد المعالجة'),
            ('matched', 'تمت المطابقة'),
            ('failed', 'فشلت المعالجة'),
        ],
        string='حالة معالجة OCR',
        default='pending',
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='ثقة استخراج OCR',
    )
    matched_by_ocr = fields.Boolean(
        string='نجاح الاستخراج الآلي؟',
        default=False,
    )
    move_id = fields.Many2one(
        'account.move',
        string='رابط الفاتورة',
        ondelete='set null',
    )
    created_by = fields.Many2one(
        'res.users',
        string='رافع الإشعار',
        default=lambda self: self.env.uid,
    )

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError('المبلغ يجب أن يكون أكبر من صفر!')

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError('نسبة ثقة OCR يجب أن تكون بين 0 و 1!')
