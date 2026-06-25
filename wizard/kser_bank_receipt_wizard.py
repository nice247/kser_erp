import base64
import logging
from datetime import datetime

import requests

from odoo import models, fields
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class KserBankReceiptWizard(models.TransientModel):
    _name = 'kser.bank.receipt.wizard'
    _description = 'معالج استخراج بيانات الإشعار البنكي'

    receipt_image = fields.Binary(
        string='صورة الإشعار البنكي',
        required=True,
    )
    receipt_image_filename = fields.Char(
        string='اسم الملف',
    )
    campaign_id = fields.Many2one(
        'project.project',
        string='الحملة المرتبطة',
    )

    extracted_transaction_id = fields.Char(string='رقم العملية المستخرج', readonly=True)
    extracted_amount = fields.Float(string='المبلغ المستخرج', readonly=True)
    extracted_bank_name = fields.Char(string='اسم البنك المستخرج', readonly=True)
    extracted_sender_account = fields.Char(string='حساب المرسل المستخرج', readonly=True)
    extracted_receiver_account = fields.Char(string='حساب المستلم المستخرج', readonly=True)
    extracted_date = fields.Char(string='تاريخ العملية المستخرج', readonly=True)
    extracted_confidence = fields.Float(string='نسبة الثقة', readonly=True)

    state = fields.Selection(
        [
            ('upload', 'رفع الصورة'),
            ('review', 'مراجعة البيانات'),
        ],
        string='المرحلة',
        default='upload',
    )

    def action_extract_data(self):
        self.ensure_one()

        if not self.receipt_image:
            raise UserError('يرجى رفع صورة الإشعار البنكي!')

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'kser_erp.spring_boot_api_key', default='',
        )

        image_bytes = base64.b64decode(self.receipt_image)

        try:
            response = requests.post(
                'http://localhost:8080/api/v1/ocr/process',
                files={'image': ('receipt.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error('Bank receipt OCR request failed: %s', str(e))
            raise UserError('فشل الاتصال بخدمة OCR: %s' % str(e))

        result = response.json()

        if not result.get('success'):
            errors = result.get('data', {}).get('errors', [])
            raise UserError('فشل استخراج البيانات: %s' % ', '.join(errors or [result.get('message', '')]))

        data = result.get('data', {})

        self.write({
            'extracted_transaction_id': data.get('transactionId', ''),
            'extracted_amount': data.get('amount', 0.0),
            'extracted_bank_name': data.get('bankName', ''),
            'extracted_sender_account': data.get('senderAccount', ''),
            'extracted_receiver_account': data.get('receiverAccount', ''),
            'extracted_date': data.get('date', ''),
            'extracted_confidence': data.get('ocr_confidence', 0.0),
            'state': 'review',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_confirm_and_save(self):
        self.ensure_one()

        if not self.extracted_transaction_id:
            raise UserError('لا يوجد رقم عملية مستخرج!')

        existing = self.env['kser.cash.donation'].search([
            ('transaction_number', '=', self.extracted_transaction_id),
        ], limit=1)

        if existing:
            raise UserError(
                'رقم العملية "%s" مسجل مسبقاً!' % self.extracted_transaction_id
            )

        donation_date = fields.Date.today()
        if self.extracted_date:
            for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
                try:
                    donation_date = datetime.strptime(self.extracted_date, fmt).date()
                    break
                except ValueError:
                    continue

        donation = self.env['kser.cash.donation'].create({
            'campaign_id': self.campaign_id.id if self.campaign_id else False,
            'amount': self.extracted_amount,
            'transaction_number': self.extracted_transaction_id,
            'bank_name': self.extracted_bank_name or '-',
            'sender_account_number': self.extracted_sender_account or '-',
            'receiver_account_number': self.extracted_receiver_account or '-',
            'donation_date': donation_date,
            'receipt_image': self.receipt_image,
            'ocr_status': 'matched',
            'ocr_confidence': self.extracted_confidence,
            'matched_by_ocr': True,
            'created_by': self.env.uid,
        })

        return {'type': 'ir.actions.act_window_close'}
