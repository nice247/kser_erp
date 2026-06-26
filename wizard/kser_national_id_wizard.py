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

    id_image = fields.Binary(
        string='National ID Image',
        required=True,
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

    state = fields.Selection(
        [
            ('upload', 'Upload Image'),
            ('review', 'Review Data'),
        ],
        string='Stage',
        default='upload',
    )

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
                f'{base_url}/api/v1/ocr/id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'Authorization': f'Bearer {api_key}'},
                timeout=30,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            _logger.error('National ID OCR request failed: %s', str(e))
            raise UserError(_('Connection failed: %s') % str(e))

        result = response.json()

        if not result.get('success'):
            errors = result.get('data', {}).get('errors', [])
            error_msg = ', '.join(errors or [result.get('message', '')])
            raise UserError(_('Data extraction failed: %s') % error_msg)

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
            'name': self.extracted_name or _('New Beneficiary'),
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
