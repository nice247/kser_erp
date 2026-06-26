from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class KserCashDonation(models.Model):
    _name = 'kser.cash.donation'
    _description = 'Cash Donation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'transaction_number'
    _sql_constraints = [
        ('transaction_number_unique', 'UNIQUE(transaction_number)', 'This Bank Transaction ID is already registered!'),
    ]

    campaign_id = fields.Many2one(
        'project.project',
        string='Linked Campaign',
        index=True,
        ondelete='set null',
        tracking=True,
    )
    amount = fields.Monetary(
        string='Amount',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id.id,
    )
    transaction_number = fields.Char(
        string='Bank Transaction ID',
        size=50,
        required=True,
        tracking=True,
    )
    bank_name = fields.Char(
        string='Bank Name',
        size=20,
        required=True,
    )
    sender_account_number = fields.Char(
        string='Sender Account Number',
        size=30,
        required=True,
    )
    receiver_account_number = fields.Char(
        string='Receiver Account Number',
        size=30,
        required=True,
    )
    donation_date = fields.Date(
        string='Donation Date',
        required=True,
        index=True,
        tracking=True,
    )
    receipt_image = fields.Binary(
        string='Bank Receipt Image',
        attachment=True,
    )
    ocr_status = fields.Selection(
        [
            ('pending', 'Pending'),
            ('matched', 'Matched'),
            ('failed', 'Failed'),
        ],
        string='OCR Status',
        default='pending',
        index=True,
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='OCR Confidence',
    )
    matched_by_ocr = fields.Boolean(
        string='Matched via OCR?',
        default=False,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Linked Invoice',
        ondelete='set null',
    )
    created_by = fields.Many2one(
        'res.users',
        string='Uploaded By',
        default=lambda self: self.env.uid,
    )

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('Amount must be greater than zero!'))

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError(_('OCR confidence must be between 0 and 1!'))
