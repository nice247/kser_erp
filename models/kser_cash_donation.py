from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class KserCashDonation(models.Model):
    _name = 'kser.cash.donation'
    _description = 'Cash Donation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'transaction_number'
    _sql_constraints = [
        ('transaction_number_unique', 'UNIQUE(transaction_number)', 'رقم المعاملة البنكية هذا مسجل بالفعل!'),
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
    ai_match_status = fields.Selection(
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
                raise ValidationError(_('يجب أن يكون المبلغ أكبر من صفر!'))



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
        """Creates an account.move (Journal Entry) directly to record Donation Income."""
        for rec in self:
            if rec.state != 'draft':
                continue
            if not rec.partner_id:
                raise ValidationError(_("يرجى اختيار المتبرع (جهة الاتصال) قبل التأكيد."))

            # Find a suitable bank/cash journal
            journal = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
            
            if not journal:
                raise ValidationError(_("لم يتم العثور على دفتر يومية بنك أو نقدية لهذه الشركة."))
            
            if not journal.default_account_id:
                raise ValidationError(_("دفتر اليومية (البنك/النقدية) المختار ليس لديه حساب افتراضي مهيأ."))

            # Find Income Account
            income_account = self.env['account.account'].search([
                ('code', '=', '41001'),
                ('company_ids', '=', self.env.company.id)
            ], limit=1)
            
            if not income_account:
                income_account = self.env['account.account'].search([
                    ('account_type', '=', 'income'),
                    ('company_ids', '=', self.env.company.id)
                ], limit=1)
            
            if not income_account:
                raise ValidationError(_("لم يتم العثور على حساب 'إيرادات' (Income) في شجرة الحسابات. يرجى تهيئة الحسابات أولاً."))

            move_vals = {
                'move_type': 'entry',
                'date': rec.donation_date,
                'journal_id': journal.id,
                'ref': f"Donation: {rec.transaction_number}",
                'line_ids': [
                    (0, 0, {
                        'name': f"Donation Receipt from {rec.partner_id.name}",
                        'account_id': journal.default_account_id.id,
                        'debit': rec.amount,
                        'credit': 0.0,
                        'partner_id': rec.partner_id.id,
                    }),
                    (0, 0, {
                        'name': f"Donation Income: {rec.transaction_number}",
                        'account_id': income_account.id,
                        'debit': 0.0,
                        'credit': rec.amount,
                        'partner_id': rec.partner_id.id,
                    }),
                ]
            }
            move = self.env['account.move'].create(move_vals)
            move.action_post()

            rec.write({
                'payment_id': False,
                'move_id': move.id,
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
