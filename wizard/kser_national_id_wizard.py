import base64
import logging
from datetime import datetime

import requests

from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools.translate import _


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
    _description = 'National ID Extraction Wizard'

    target_type = fields.Selection([
        ('beneficiary', 'Beneficiary'),
        ('volunteer', 'Volunteer'),
    ], string='Target Type', default='beneficiary')

    id_image = fields.Binary(
        string='National ID Image',
    )
    id_image_filename = fields.Char(
        string='File Name',
    )

    extracted_name = fields.Char(string='Extracted Name')
    extracted_national_id = fields.Char(string='Extracted National ID')
    extracted_profession = fields.Char(string='Extracted Profession')
    extracted_marital_status = fields.Char(string='Extracted Marital Status')
    extracted_dob = fields.Char(string='Extracted Date of Birth')
    extracted_gender = fields.Char(string='Extracted Gender')
    extracted_confidence = fields.Float(string='OCR Confidence', readonly=True)

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

        if not self.id_image:
            raise UserError(_('Please upload the National ID image!'))

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('API credentials (kser.springboot_api_key or kser.springboot_base_url) are not configured!'))

        base_url = base_url.rstrip('/')

        image_bytes = base64.b64decode(self.id_image)

        try:
            response = requests.post(
                f'{base_url}/api/v1/ocr/national-id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            _logger.error('National ID OCR request failed: %s', str(e))
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
            raise UserError(_('No extracted National ID!'))

        if self.target_type == 'volunteer':
            existing_partner = self.env['res.partner'].search([
                ('national_id_number', '=', self.extracted_national_id),
            ], limit=1)

            volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)

            if existing_partner:
                existing_partner.write({
                    'name': self.extracted_name or existing_partner.name,
                    'national_id_image': self.id_image,
                    'category_tag': volunteer_tag.id if volunteer_tag else False,
                })
            else:
                self.env['res.partner'].create({
                    'name': self.extracted_name or _('New Volunteer'),
                    'national_id_number': self.extracted_national_id,
                    'national_id_image': self.id_image,
                    'category_tag': volunteer_tag.id if volunteer_tag else False,
                })
            return {'type': 'ir.actions.act_window_close'}

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
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)

        if existing:
            partner = existing.partner_id
            partner.write({
                'name': self.extracted_name or partner.name,
                'category_tag': beneficiary_tag.id if beneficiary_tag else partner.category_tag.id,
            })

            existing.write({
                'national_id_image': self.id_image,
                'profession': self.extracted_profession or existing.profession,
                'marital_status': marital_key or existing.marital_status,
                'birthdate': birthdate or existing.birthdate,
                'ocr_confidence': self.extracted_confidence,
            })

            return {'type': 'ir.actions.act_window_close'}

        partner = self.env['res.partner'].create({
            'name': self.extracted_name or _('New Beneficiary'),
            'category_tag': beneficiary_tag.id if beneficiary_tag else False,
            'national_id_number': self.extracted_national_id,
            'national_id_image': self.id_image,
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
