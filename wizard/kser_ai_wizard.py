import logging

import requests

from odoo import models, fields


_logger = logging.getLogger(__name__)


class KserAiWizard(models.TransientModel):
    _name = 'kser.ai.wizard'
    _description = 'معالج الاقتراحات الذكية'

    campaign_id = fields.Many2one(
        'project.project',
        string='الحملة',
    )

    def action_get_ai_suggestions(self):
        self.ensure_one()

        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
            ('product_id.categ_id.name', '=', 'أدوية'),
        ])

        medicines = []
        for quant in quants:
            expiry = False
            if quant.lot_id and quant.lot_id.expiration_date:
                expiry = quant.lot_id.expiration_date.strftime('%Y-%m-%d')

            medicines.append({
                'drug_name': quant.product_id.name,
                'available_qty': quant.quantity,
                'expiration_date': expiry,
            })

        beneficiary_records = self.env['kser.beneficiary'].search([
            ('health_conditions', '!=', False),
        ])

        beneficiaries = []
        for ben in beneficiary_records:
            beneficiaries.append({
                'beneficiary_id': ben.id,
                'health_conditions': ben.health_conditions,
            })

        payload = {
            'medicines': medicines,
            'beneficiaries': beneficiaries,
        }

        api_key = self.env['ir.config_parameter'].sudo().get_param(
            'kser_erp.spring_boot_api_key', default='',
        )

        try:
            response = requests.post(
                'http://localhost:8080/api/v1/ai/match',
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'X-API-KEY': api_key,
                },
                timeout=30,
            )
            response.raise_for_status()
            # TODO: Parse response.json() and create stock.picking / stock.move
            # records based on the AI recommendations returned by Spring Boot.
        except requests.exceptions.RequestException as e:
            _logger.error('AI matching API request failed: %s', str(e))

        return {'type': 'ir.actions.act_window_close'}
