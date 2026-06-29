import base64
import requests
import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _sql_constraints = [
        ('kser_national_id_unique', 'UNIQUE(national_id_number)',
         'This National ID is already registered to another volunteer!'),
    ]

    category_tag = fields.Many2one(
        'res.partner.category',
        string='Contact Category',
        index=True,
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='Field Supervisor',
        domain=lambda self: [('groups_id', 'in', [self.env.ref('kser_erp.group_field_supervisor', raise_if_not_found=False).id])] if self.env.ref('kser_erp.group_field_supervisor', raise_if_not_found=False) else [],
        index=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
    )
    is_volunteer = fields.Boolean(
        compute='_compute_role_booleans',
    )
    is_donor = fields.Boolean(
        compute='_compute_role_booleans',
    )
    is_beneficiary = fields.Boolean(
        compute='_compute_role_booleans',
    )

    @api.depends('category_tag')
    def _compute_role_booleans(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        donor_tag = self.env.ref('kser_erp.partner_category_donor', raise_if_not_found=False)
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
        for rec in self:
            rec.is_volunteer = (rec.category_tag == volunteer_tag) if volunteer_tag else False
            rec.is_donor = (rec.category_tag == donor_tag) if donor_tag else False
            rec.is_beneficiary = (rec.category_tag == beneficiary_tag) if beneficiary_tag else False
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
    )

    @api.constrains('national_id_number', 'national_id_image', 'category_tag')
    def _check_national_id_volunteer(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        for rec in self:
            if volunteer_tag and rec.category_tag == volunteer_tag:
                if not rec.national_id_number and not rec.national_id_image:
                    continue
                if not rec.national_id_image:
                    raise ValidationError(_("يجب رفع صورة الرقم الوطني للمتطوع!"))
                if not rec.national_id_number or len(rec.national_id_number) != 11 or not rec.national_id_number.isdigit():
                    raise ValidationError(_("يجب أن يتكون الرقم الوطني للمتطوع من 11 خانة رقمية فقط!"))

    task_ids = fields.One2many(
        'project.task',
        'volunteer_id',
        string='Volunteer Tasks',
    )
    donation_ids = fields.One2many(
        'kser.cash.donation',
        'partner_id',
        string='Donations',
    )

    task_count = fields.Integer(
        compute='_compute_task_count',
        string='Tasks Count',
    )
    donation_count = fields.Integer(
        compute='_compute_donation_count',
        string='Donations Count',
    )

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.depends('donation_ids')
    def _compute_donation_count(self):
        for rec in self:
            rec.donation_count = len(rec.donation_ids)

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'name': _('Assigned Tasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('volunteer_id', '=', self.id)],
            'context': {'default_volunteer_id': self.id},
        }

    def action_view_donations(self):
        self.ensure_one()
        return {
            'name': _('Donations'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.cash.donation',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }

    def action_ocr_extract(self):
        self.ensure_one()
        if not self.national_id_image:
            raise UserError(_('يجب رفع صورة الهوية الوطنية أولاً في قسم "بيانات الهوية" قبل محاولة قراءة البيانات.'))

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('API credentials (kser.springboot_api_key or kser.springboot_base_url) are not configured!'))

        base_url = base_url.rstrip('/')
        image_bytes = base64.b64decode(self.national_id_image)

        try:
            response = requests.post(
                f'{base_url}/api/v1/ocr/national-id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
            result = response.json()
        except Exception as e:
            raise UserError(_('OCR Service failed: %s') % str(e))

        if not result.get('success'):
            backend_msg = result.get('message', '')
            errors = result.get('data', {}).get('errors', [])
            detailed_errors = ', '.join(errors) if errors else ''
            error_msg = f"{backend_msg} (Details: {detailed_errors})" if detailed_errors else backend_msg
            raise UserError(error_msg or _('Failed to extract data.'))

        data = result.get('data', {})
        self.write({
            'name': data.get('name') or self.name,
            'national_id_number': data.get('nationalIdNumber') or self.national_id_number,
        })
