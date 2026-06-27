import logging

import requests

from odoo import models, fields
from odoo.exceptions import UserError
from odoo.tools.translate import _


_logger = logging.getLogger(__name__)


class KserAiWizard(models.TransientModel):
    _name = 'kser.ai.wizard'
    _description = 'Smart Suggestions Wizard'

    campaign_id = fields.Many2one(
        'project.project',
        string='Campaign',
    )

    def action_get_ai_suggestions(self):
        self.ensure_one()

        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
            ('product_id.categ_id.name', '=', 'أدوية'), # Keep this in Arabic if it refers to actual category name in DB, but usually categories are translated via view. We'll leave the code value alone or we should change the condition if the actual record name changes. Let's keep it as is since it's data matching.
        ])

        inventory = []
        for quant in quants:
            inventory.append({
                'id': quant.product_id.id,
                'itemName': quant.product_id.name,
                'quantity': int(quant.quantity),
            })

        beneficiary_records = self.env['kser.beneficiary'].search([
            ('health_conditions', '!=', False),
        ])

        beneficiaries = []
        for ben in beneficiary_records:
            beneficiaries.append({
                'id': ben.id,
                'name': ben.partner_id.name,
                'chronicDisease': ben.health_conditions,
            })

        payload = {
            'inventory': inventory,
            'beneficiaries': beneficiaries,
        }

        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')

        if not api_key or not base_url:
            raise UserError(_('API credentials (kser.springboot_api_key or kser.springboot_base_url) are not configured!'))

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
            response.raise_for_status()
            # TODO: Parse response.json()['recommendations'] and create
            # stock.picking / stock.move records for approved matches.
        except requests.exceptions.RequestException as e:
            _logger.error('AI matching API request failed: %s', str(e))
            raise UserError(_('Connection failed: %s') % str(e))

        return {'type': 'ir.actions.act_window_close'}
