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
        # هذه الدالة مسؤولة عن استخراج البيانات من صورة الإيصال المرفقة باستخدام تقنية الذكاء الاصطناعي
        # تدعم الدالة حالياً استخراج البيانات عبر نموذج Gemini
        self.ensure_one()

        if not self.receipt_image:
            raise UserError(_('يرجى رفع صورة الإيصال البنكي!'))

        # محاولة الحصول على مفتاح الـ API لـ Gemini من إعدادات النظام
        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.gemini_api_key')
        if not api_key:
            api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')

        if not api_key:
            raise UserError(_('مفتاح Gemini API غير مهيأ. يرجى مراجعة مسؤول النظام.'))

        # Prepare Gemini Request
        prompt = """
أنت خبير في استخراج البيانات من إيصالات التحويل البنكي والمالي.
قم بتحليل الإيصال المرفق لتحديد ما إذا كان إيصال "بنكك" (Bankak / Bank of Khartoum) أو إيصال "فوري" (Fawry / FISB / البنك الإسلامي السوداني)، ثم استخرج البيانات بصيغة JSON فقط، مع مراعاة أن الإيصال قد يكون باللغة العربية أو الإنجليزية:

البيانات المطلوبة في الـ JSON:
- transactionId: رقم المعاملة (يقابله في الإيصال: Reference Number, Trx. ID, رقم العملية, أو الرقم المرجعي) (سلسلة نصية).
- senderAccount: الحساب المرسل (يقابله في الإيصال: From Account, من الحساب, أو من حساب) (سلسلة نصية).
- amount: المبلغ المحول (يقابله في الإيصال: Amount أو المبلغ) (رقم عشري، تأكد من استخراجه بشكل صحيح بدون فواصل الآلاف).
- date: تاريخ المعاملة (يقابله في الإيصال: Date, Date & Time, التاريخ, أو التاريخ و الزمن) (حوله دائمًا ليكون بصيغة YYYY-MM-DD).
- receiverAccount: الحساب المستقبل أو رقمه (يقابله في الإيصال: To Account, الي الحساب, أو الى حساب) (سلسلة نصية).
- bankName: اسم البنك أو مزود الخدمة (سلسلة نصية، مثل "بنك الخرطوم" لبنكك، و"بنك فيصل الاسلامي" لفوري).

طريقة استخراج البيانات ومعالجتها لكل إيصال:

أولاً: إذا كان الإيصال يخص "بنكك" (Bankak / بنك الخرطوم):
- حدد bankName كـ "BOK".
- المعالجة المطلوبة لأرقام الحسابات (senderAccount و receiverAccount):
  بعد استخراج الرقم من الحقول المناسبة، قم بـ:
  1. إزالة جميع المسافات الفارغة من الرقم.
  2. ابدأ العد من اليسار وصولاً إلى الخانة رقم 6، واستخرج 7 أرقام متتالية فقط (بدءاً من هذه الخانة السادسة)، ليكون هذا هو الرقم النهائي للحساب.

ثانياً: إذا كان الإيصال يخص "فوري" (Fawry / FISB):
- حدد bankName كـ "FISB".
- المعالجة المطلوبة لأرقام الحسابات (senderAccount و receiverAccount):
  بعد استخراج الرقم من الحقول المناسبة، قم بـ:
  1. إزالة جميع المسافات الفارغة من الرقم.
  2. ابدأ العد من اليسار وصولاً إلى الخانة رقم 10، واستخرج 8 أرقام متتالية فقط (بدءاً من الخانة العاشرة)، ليكون هذا هو الرقم النهائي للحساب.

ثالثاً: اذا لم يكن اي منهم استخرج البيانات وارجع ارقام الحساب كما هي.

لا تضف أي نص، أو مقدمات، أو شروحات خارج هيكل الـ JSON المنسق.
"""
        payload = {
            "contents": [{
                "parts": [
                    {"text": prompt},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": self.receipt_image.decode('utf-8') if isinstance(self.receipt_image, bytes) else self.receipt_image
                        }
                    }
                ]
            }],
            "generationConfig": {
                "temperature": 0.1
            }
        }
        
        url = f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}'
        headers = {'Content-Type': 'application/json'}

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error('Gemini API request failed: %s - %s', str(e), response.text if hasattr(e, 'response') and e.response else '')
            raise UserError(_('فشل الاتصال بخادم Gemini. يرجى المحاولة مرة أخرى أو الاتصال بمسؤول النظام.'))

        try:
            result = response.json()
            text_response = result['candidates'][0]['content']['parts'][0]['text'].strip()
            
            # Clean markdown code blocks if any
            if text_response.startswith('```json'):
                text_response = text_response[7:]
            elif text_response.startswith('```'):
                text_response = text_response[3:]
            
            if text_response.endswith('```'):
                text_response = text_response[:-3]
                
            text_response = text_response.strip()
            
            import json
            data = json.loads(text_response)
        except (Exception, ValueError, KeyError, IndexError) as e:
            _logger.error('Failed to parse Gemini response: %s', str(e))
            raise UserError(_("تلقى النظام استجابة غير صالحة. يرجى التأكد من وضوح الصورة والمحاولة مرة أخرى، أو إدخال البيانات يدوياً."))

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
            raise UserError(_('لم يتم استخراج رقم المعاملة من الصورة!'))

        existing = self.env['kser.cash.donation'].search([
            ('transaction_number', '=', self.extracted_transaction_id),
        ], limit=1)

        if existing:
            raise UserError(
                _('رقم المعاملة "%s" مسجل بالفعل!') % self.extracted_transaction_id
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
            'ai_match_status': 'matched',
            'matched_by_ocr': True,
            'created_by': self.env.uid,
        })

        return {'type': 'ir.actions.act_window_close'}
