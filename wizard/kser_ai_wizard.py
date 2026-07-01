import logging
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class KserAiWizard(models.TransientModel):
    _name = 'kser.ai.wizard'
    _description = 'Stock Gap Analysis Wizard'

    name = fields.Char(
        string='Name',
        default='فحص حالة المخزون (AI)',
    )
    campaign_id = fields.Many2one(
        'project.project',
        string='Campaign',
        required=False,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('result', 'Result'),
        ],
        string='Status',
        default='draft',
    )
    urgency_report = fields.Text(
        string='Urgency Report',
    )
    summary = fields.Text(
        string='Summary',
    )
    uncovered_case_ids = fields.One2many(
        'kser.ai.uncovered.case',
        'wizard_id',
        string='Uncovered Cases',
    )

    @api.model
    def action_open_wizard(self):
        wizard = self.search([], limit=1, order='id desc')
        if not wizard:
            wizard = self.create({'state': 'draft'})
        else:
            wizard.write({
                'state': 'draft',
                'summary': '',
                'urgency_report': '',
            })
            wizard.uncovered_case_ids.unlink()

        return {
            'type': 'ir.actions.act_window',
            'name': _('فحص حالة المخزون (AI)'),
            'res_model': 'kser.ai.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_get_ai_suggestions(self):
        self.ensure_one()

        if not (self.env.user.has_group('kser_erp.group_admin_supervisor') or 
                self.env.user.has_group('kser_erp.group_clinic_manager') or 
                self.env.user.has_group('kser_erp.group_system_admin')):
            raise UserError(_("عذراً، هذا الإجراء مخصص للمشرف الإداري العام أو مدير العيادة فقط."))

        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ])

        inventory = []
        for quant in quants:
            inventory.append({
                'id': quant.product_id.id,
                'itemName': quant.product_id.name,
                'activeIngredient': quant.product_id.active_ingredient or '',
                'medicalIndications': quant.product_id.medical_indications or '',
                'contraindications': quant.product_id.contraindications or '',
                'quantity': int(quant.quantity),
            })

        beneficiary_records = self.env['kser.beneficiary'].search([
            ('health_conditions', '!=', False),
        ])

        beneficiaries = []
        for ben in beneficiary_records:
            beneficiaries.append({
                'id': ben.id,
                'health_conditions': ben.health_conditions,
            })

        payload = {
            'inventory': inventory,
            'beneficiaries': beneficiaries,
        }

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('بيانات الاتصال بالنظام غير مهيأة. يرجى مراجعة مسؤول النظام.'))

        base_url = base_url.rstrip('/')

        try:
            response = requests.post(
                f'{base_url}/api/v1/ai/match-inventory',
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-API-KEY': api_key,
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as e:
            _logger.error('AI matching API request failed: %s', str(e))
            raise UserError(_('فشل الاتصال بالخادم. يرجى المحاولة مرة أخرى أو الاتصال بمسؤول النظام.'))

        try:
            result = response.json()
        except Exception:
            raise UserError(_('تلقى النظام استجابة غير صالحة من الخادم. يرجى الاتصال بمسؤول النظام.'))

        self.uncovered_case_ids.unlink()

        urgency_report = result.get('urgency_report') or result.get('urgencyReport') or ''
        summary_text = result.get('summary') or ''

        uncovered_cases_data = result.get('uncovered_cases') or result.get('uncoveredCases') or []
        for case in uncovered_cases_data:
            ben_id = case.get('beneficiary_id') or case.get('beneficiaryId')
            h_cond = case.get('health_conditions') or case.get('healthConditions') or ''
            med = case.get('needed_medicine') or case.get('neededMedicine') or ''
            just = case.get('justification') or case.get('reason') or ''
            if ben_id:
                ben = self.env['kser.beneficiary'].browse(ben_id)
                if ben.exists():
                    self.env['kser.ai.uncovered.case'].create({
                        'wizard_id': self.id,
                        'beneficiary_id': ben.id,
                        'health_conditions': h_cond,
                        'needed_medicine': med,
                        'justification': just,
                    })

        self.write({
            'summary': summary_text,
            'urgency_report': urgency_report,
            'state': 'result',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'kser.ai.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class KserAiUncoveredCase(models.TransientModel):
    _name = 'kser.ai.uncovered.case'
    _description = 'AI Uncovered Case'

    wizard_id = fields.Many2one(
        'kser.ai.wizard',
        string='Wizard',
        ondelete='cascade',
    )
    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Beneficiary',
        required=True,
    )
    national_id_number = fields.Char(
        related='beneficiary_id.national_id_number',
        string='National ID Number',
        readonly=True,
    )
    health_conditions = fields.Text(
        string='Health Conditions',
    )
    needed_medicine = fields.Char(
        string='Needed Medicine',
    )
    justification = fields.Text(
        string='Justification',
    )
