import base64
import logging
from datetime import datetime

import requests

from odoo import models, fields
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)

MARITAL_STATUS_MAP = {
    'أعزب': 'single',
    'متزوج': 'married',
    'متزوجة': 'married',
    'أرمل': 'widowed',
    'أرملة': 'widowed',
    'أرمل/ة': 'widowed',
    'مطلق': 'divorced',
    'مطلقة': 'divorced',
    'مطلق/ة': 'divorced',
}


class KserNationalIdWizard(models.TransientModel):
    _name = 'kser.national.id.wizard'
    _description = 'معالج استخراج بيانات الهوية'

    id_image = fields.Binary(
        string='صورة الرقم الوطني',
        required=True,
    )
    id_image_filename = fields.Char(
        string='اسم الملف',
    )

    extracted_name = fields.Char(string='الاسم المستخرج')
    extracted_national_id = fields.Char(string='الرقم الوطني المستخرج')
    extracted_profession = fields.Char(string='المهنة المستخرجة')
    extracted_marital_status = fields.Char(string='الحالة الاجتماعية المستخرجة')
    extracted_dob = fields.Char(string='تاريخ الميلاد المستخرج')
    extracted_gender = fields.Char(string='الجنس المستخرج')
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

        if not self.id_image:
            raise UserError('يرجى رفع صورة الرقم الوطني!')

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'kser_erp.spring_boot_api_key', default='',
        )

        image_bytes = base64.b64decode(self.id_image)

        try:
            response = requests.post(
                'http://localhost:8080/api/v1/ocr/national-id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error('National ID OCR request failed: %s', str(e))
            raise UserError('فشل الاتصال بخدمة OCR: %s' % str(e))

        result = response.json()

        if not result.get('success'):
            errors = result.get('data', {}).get('errors', [])
            raise UserError('فشل استخراج البيانات: %s' % ', '.join(errors or [result.get('message', '')]))

        data = result.get('data', {})

        self.write({
            'extracted_name': data.get('name', ''),
            'extracted_national_id': data.get('nationalIdNumber', ''),
            'extracted_profession': data.get('profession', ''),
            'extracted_marital_status': data.get('maritalStatus', ''),
            'extracted_dob': data.get('dateOfBirth', ''),
            'extracted_gender': data.get('gender', ''),
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

        if not self.extracted_national_id:
            raise UserError('لا يوجد رقم وطني مستخرج!')

        existing = self.env['kser.beneficiary'].search([
            ('national_id_number', '=', self.extracted_national_id),
        ], limit=1)

        birthdate = False
        if self.extracted_dob:
            for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    birthdate = datetime.strptime(self.extracted_dob, fmt).date()
                    break
                except ValueError:
                    continue

        marital_key = MARITAL_STATUS_MAP.get(self.extracted_marital_status, False)

        if existing:
            partner = existing.partner_id
            partner.write({'name': self.extracted_name or partner.name})

            existing.write({
                'national_id_image': self.id_image,
                'profession': self.extracted_profession or existing.profession,
                'marital_status': marital_key or existing.marital_status,
                'birthdate': birthdate or existing.birthdate,
                'ocr_confidence': self.extracted_confidence,
            })

            return {'type': 'ir.actions.act_window_close'}

        partner = self.env['res.partner'].create({
            'name': self.extracted_name or 'مستفيد جديد',
        })

        self.env['kser.beneficiary'].create({
            'partner_id': partner.id,
            'national_id_number': self.extracted_national_id,
            'national_id_image': self.id_image,
            'profession': self.extracted_profession or False,
            'marital_status': marital_key,
            'birthdate': birthdate,
            'ocr_confidence': self.extracted_confidence,
            'district': '-',
            'registered_by': self.env.uid,
        })

        return {'type': 'ir.actions.act_window_close'}
