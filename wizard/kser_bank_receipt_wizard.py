import base64
import logging
from datetime import datetime

import requests

from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools.translate import _


_logger = logging.getLogger(__name__)


class KserBankReceiptWizard(models.TransientModel):
    _name = 'kser.bank.receipt.wizard'
    _description = 'Bank Receipt Extraction Wizard'

    receipt_image = fields.Binary(
        string='Bank Receipt Image',
    )
    receipt_image_filename = fields.Char(
        string='File Name',
    )
    campaign_id = fields.Many2one(
        'project.project',
        string='Linked Campaign',
    )

    extracted_transaction_id = fields.Char(string='Extracted Transaction ID')
    extracted_amount = fields.Float(string='Extracted Amount')
    extracted_bank_name = fields.Char(string='Extracted Bank Name')
    extracted_sender_account = fields.Char(string='Extracted Sender Account')
    extracted_receiver_account = fields.Char(string='Extracted Receiver Account')
    extracted_date = fields.Char(string='Extracted Date')


    is_manual_entry = fields.Boolean(
        string='Manual Entry',
        default=False,
    )

    state = fields.Selection(
        [
            ('upload', 'Upload Image'),
            ('review', 'Review Data'),
        ],
        string='Stage',
        default='upload',
    )

    def action_manual_entry(self):
        """Skip OCR and go directly to manual data entry."""
        self.ensure_one()
        self.write({
            'state': 'review',
            'is_manual_entry': True,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_extract_data(self):
        self.ensure_one()

        if not self.receipt_image:
            raise UserError(_('Please upload the bank receipt image!'))

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('API credentials (kser.springboot_api_key or kser.springboot_base_url) are not configured!'))

        base_url = base_url.rstrip('/')

        image_bytes = base64.b64decode(self.receipt_image)

        try:
            response = requests.post(
                f'{base_url}/api/v1/ocr/process',
                files={'image': ('receipt.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            _logger.error('Bank receipt OCR request failed: %s', str(e))
            raise UserError(_('Connection failed: %s') % str(e))

        try:
            result = response.json()
        except Exception:
            raise UserError(_('Invalid response from server: %s') % response.text)

        if not result.get('success'):
            backend_msg = result.get('message', '')
            errors = result.get('data', {}).get('errors', [])
            detailed_errors = ', '.join(errors) if errors else ''
            
            if backend_msg and detailed_errors:
                error_msg = f"{backend_msg} \n(التفاصيل: {detailed_errors})"
            elif backend_msg:
                error_msg = backend_msg
            else:
                error_msg = detailed_errors or "حدث خطأ غير معروف أثناء المعالجة."
                
            raise UserError(f"فشلت عملية استخراج البيانات:\n{error_msg}")

        data = result.get('data', {})

        self.write({
            'extracted_transaction_id': data.get('transactionId', ''),
            'extracted_amount': data.get('amount', 0.0),
            'extracted_bank_name': data.get('bankName', ''),
            'extracted_sender_account': data.get('senderAccount', ''),
            'extracted_receiver_account': data.get('receiverAccount', ''),
            'extracted_date': data.get('date', ''),
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
            raise UserError(_('No extracted transaction ID!'))

        existing = self.env['kser.cash.donation'].search([
            ('transaction_number', '=', self.extracted_transaction_id),
        ], limit=1)

        if existing:
            raise UserError(
                _('Transaction ID "%s" is already registered!') % self.extracted_transaction_id
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
            'matched_by_ocr': True,
            'created_by': self.env.uid,
        })

        return {'type': 'ir.actions.act_window_close'}
