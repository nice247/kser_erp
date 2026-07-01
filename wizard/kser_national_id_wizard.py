import base64
import logging
from datetime import datetime

import requests

from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools.translate import _


_logger = logging.getLogger(__name__)

MARITAL_STATUS_MAP = {
    'غير متزوج': 'single',
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

    extracted_name = fields.Char(string='الاسم الكامل')
    extracted_national_id = fields.Char(string='رقم الهوية الوطنية')
    extracted_profession = fields.Char(string='المهنة')
    extracted_marital_status = fields.Char(string='الحالة الاجتماعية')
    extracted_dob = fields.Char(string='تاريخ الميلاد')
    extracted_gender = fields.Char(string='الجنس')
    extracted_mother_name = fields.Char(string='اسم الوالدة')


    is_manual_entry = fields.Boolean(
        string='Manual Entry',
        default=False,
    )
    is_child = fields.Boolean(
        string='Is Child',
        default=False,
    )
    is_disabled = fields.Boolean(
        string='Disabled / Special Needs',
        default=False,
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='Head of Family',
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
            raise UserError(_('يرجى رفع صورة الرقم الوطني!'))

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('بيانات الاتصال بالنظام غير مهيأة. يرجى مراجعة مسؤول النظام.'))

        base_url = base_url.rstrip('/')

        image_bytes = base64.b64decode(self.id_image)

        try:
            response = requests.post(
                f'{base_url}/api/v1/vision/national-id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            _logger.error('National ID OCR request failed: %s', str(e))
            raise UserError(_('فشل الاتصال بالخادم. يرجى المحاولة مرة أخرى أو الاتصال بمسؤول النظام.'))

        try:
            result = response.json()
        except Exception:
            raise UserError(_('تلقى النظام استجابة غير صالحة من الخادم. يرجى الاتصال بمسؤول النظام.'))

        if not result.get('success'):
            backend_msg = result.get('message', '')
            errors = result.get('data', {}).get('errors', [])
            detailed_errors = ', '.join(errors) if errors else ''
            _logger.error('OCR process failed: %s (Details: %s)', backend_msg, detailed_errors)
            raise UserError(_("فشلت عملية استخراج البيانات. يرجى التأكد من وضوح صورة الهوية الوطنية والمحاولة مرة أخرى، أو إدخال البيانات يدوياً."))

        data = result.get('data', {})

        self.write({
            'extracted_name': data.get('name', ''),
            'extracted_national_id': data.get('nationalIdNumber', ''),
            'extracted_profession': data.get('profession', ''),
            'extracted_marital_status': data.get('maritalStatus', ''),
            'extracted_dob': data.get('dateOfBirth', ''),
            'extracted_gender': data.get('gender', ''),
            'extracted_mother_name': data.get('motherName', ''),
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

        if not self.is_child and not self.extracted_national_id:
            raise UserError(_('لم يتم استخراج رقم الهوية الوطنية من الصورة!'))

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

        birthdate = False
        if self.extracted_dob:
            for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    birthdate = datetime.strptime(self.extracted_dob, fmt).date()
                    break
                except ValueError:
                    continue

        if self.is_child and not birthdate:
            raise UserError(_("يجب إدخال تاريخ ميلاد الطفل لتحديد عمره!"))

        is_older_child = False
        if birthdate:
            today = fields.Date.today()
            age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
            if age >= 7:
                is_older_child = True

        if is_older_child and not self.is_manual_entry and not self.id_image:
            raise UserError(_("الطفل الذي يبلغ عمره 7 سنوات أو أكثر يجب رفع صورة الرقم الوطني له!"))

        existing = False
        if not self.is_child or is_older_child:
            if self.extracted_national_id:
                existing = self.env['kser.beneficiary'].search([
                    ('national_id_number', '=', self.extracted_national_id),
                ], limit=1)

        marital_key = MARITAL_STATUS_MAP.get(self.extracted_marital_status, False)
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)

        is_id_required = (not self.is_child) or is_older_child

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
                'extracted_mother_name': self.extracted_mother_name,
                'is_disabled': self.is_disabled,
            })

            return {'type': 'ir.actions.act_window_close'}

        partner = self.env['res.partner'].create({
            'name': self.extracted_name or _('New Beneficiary'),
            'category_tag': beneficiary_tag.id if beneficiary_tag else False,
            'national_id_number': self.extracted_national_id if is_id_required else False,
            'national_id_image': self.id_image if is_id_required else False,
        })

        self.env['kser.beneficiary'].create({
            'partner_id': partner.id,
            'national_id_number': self.extracted_national_id if is_id_required else False,
            'national_id_image': self.id_image if is_id_required else False,
            'profession': self.extracted_profession or False,
            'marital_status': marital_key,
            'birthdate': birthdate,
            'district': '-',
            'registered_by': self.env.uid,
            'extracted_mother_name': self.extracted_mother_name,
            'is_child': self.is_child,
            'head_of_family_id': self.head_of_family_id.id if self.is_child else False,
            'relationship': 'child' if self.is_child else 'self',
            'is_disabled': self.is_disabled,
        })

        return {'type': 'ir.actions.act_window_close'}
