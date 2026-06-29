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

    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('posted', 'Confirmed'),
        ],
        string='Status',
        default='draft',
        tracking=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Donor (Partner)',
        domain=[('category_tag', '!=', False)],
        tracking=True,
    )

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
        readonly=True,
    )
    matched_by_ocr = fields.Boolean(
        string='Matched via OCR?',
        default=False,
    )
    move_id = fields.Many2one(
        'account.move',
        string='Linked Journal Entry',
        ondelete='set null',
        readonly=True,
    )
    payment_id = fields.Many2one(
        'account.payment',
        string='Linked Payment',
        ondelete='set null',
        readonly=True,
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

    def _preprocess_image(self, image_base64):
        if not image_base64:
            return False
        try:
            import io
            from PIL import Image, ImageOps
            import base64
            image_bytes = base64.b64decode(image_base64)
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=95)
            return base64.b64encode(output.getvalue()).decode('utf-8')
        except Exception:
            return image_base64



    def action_confirm(self):
        """Creates an account.payment (Inbound) for this donation."""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.partner_id:
                raise ValidationError(_("Please select a Donor (Partner) before confirming."))

            # Find a suitable bank/cash journal
            journal = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            if not journal:
                raise ValidationError(_("No Bank or Cash journal found for this company."))

            payment_vals = {
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': rec.partner_id.id,
                'amount': rec.amount,
                'currency_id': rec.currency_id.id,
                'journal_id': journal.id,
                'date': rec.donation_date,
                'memo': f"Donation: {rec.transaction_number}",
            }
            payment = self.env['account.payment'].create(payment_vals)
            payment.action_post()

            rec.write({
                'payment_id': payment.id,
                'move_id': payment.move_id.id,
                'state': 'posted',
            })
            
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'create',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم إنشاء/رفع إيصال بنكي برقم معاملة: {rec.transaction_number}، بمبلغ: {rec.amount}",
            })
        return records

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            if 'state' in vals and vals['state'] == 'posted':
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'approve',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم تأكيد استلام التبرع {rec.transaction_number} مالياً. رقم قيد الدفع: {rec.payment_id.id if rec.payment_id else 'غير محدد'}",
                })
            elif vals:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'update',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم تعديل التبرع {rec.transaction_number}. الحقول المعدلة: {list(vals.keys())}",
                })
        return res

    def action_view_payment(self):
        self.ensure_one()
        if self.payment_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Linked Payment'),
                'res_model': 'account.payment',
                'view_mode': 'form',
                'res_id': self.payment_id.id,
                'target': 'current',
            }
