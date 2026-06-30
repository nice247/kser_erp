import logging
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class KserAiWizard(models.TransientModel):
    _name = 'kser.ai.wizard'
    _description = 'Smart Suggestions Wizard'

    campaign_id = fields.Many2one(
        'project.project',
        string='Campaign',
        required=True,
    )
    state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('result', 'Result'),
        ],
        string='Status',
        default='draft',
    )
    line_ids = fields.One2many(
        'kser.ai.suggestion.line',
        'wizard_id',
        string='Suggestions',
    )

    def action_get_ai_suggestions(self):
        self.ensure_one()

        # Check if campaign budget is approved
        if self.campaign_id.state != 'approved':
            raise UserError(_("لا يمكن تشغيل المطابقة الذكية. ميزانية الحملة غير معتمدة بعد!"))

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
                'name': ben.partner_id.name,
                'chronicDisease': ben.health_conditions,
                'birthdate': str(ben.birthdate) if ben.birthdate else '',
                'dateOfBirth': str(ben.birthdate) if ben.birthdate else '',
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

        # Clear old lines
        self.line_ids.unlink()

        recommendations = result.get('recommendations', [])
        if not recommendations:
            raise UserError(_("لم يتم إرجاع أي توصيات ذكية من الخادم. قد يكون المخزون والاحتياجات متطابقين بالفعل."))

        for rec in recommendations:
            product_id = rec.get('inventoryItemId') or rec.get('productId')
            matched_ben_ids = rec.get('matchedBeneficiaryIds') or rec.get('beneficiaryIds') or rec.get('matchedBeneficiaryIdList') or []
            if isinstance(matched_ben_ids, int):
                matched_ben_ids = [matched_ben_ids]
            priority_str = rec.get('priority', 'طبيعي')
            rationale = rec.get('rationale') or rec.get('reason') or rec.get('explanation') or ''

            priority_map = {
                'عاجل': 'urgent',
                'متوسط': 'medium',
                'طبيعي': 'normal',
                'urgent': 'urgent',
                'medium': 'medium',
                'normal': 'normal',
                'HIGH': 'urgent',
                'MEDIUM': 'medium',
                'LOW': 'normal',
                'high': 'urgent',
                'low': 'normal',
            }
            priority = priority_map.get(priority_str, 'normal')

            product = self.env['product.product'].browse(product_id)
            if not product.exists():
                continue

            bens = self.env['kser.beneficiary'].browse(matched_ben_ids)
            valid_ben_ids = bens.filtered(lambda b: b.exists()).ids

            if not valid_ben_ids:
                continue

            self.env['kser.ai.suggestion.line'].create({
                'wizard_id': self.id,
                'product_id': product.id,
                'beneficiary_ids': [(6, 0, valid_ben_ids)],
                'priority': priority,
                'rationale': rationale,
            })

        self.state = 'result'

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_apply(self):
        self.ensure_one()
        approved_lines = self.line_ids.filtered(lambda l: l.approved)
        if not approved_lines:
            raise UserError(_("لا توجد اقتراحات معتمدة للتوزيع."))

        # Find delivery picking type
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)

        if not picking_type:
            raise UserError(_("لم يتم العثور على نوع عملية التوزيع (شحنات صادرة)."))

        source_location = picking_type.default_location_src_id
        dest_location = picking_type.default_location_dest_id or self.env.ref('stock.stock_location_customers')

        if not source_location:
            raise UserError(_("لم يتم تهيئة موقع المصدر الافتراضي لنوع عملية التوزيع."))

        pickings_created = self.env['stock.picking']

        for line in approved_lines:
            move_vals = []
            for ben in line.beneficiary_ids:
                move_vals.append((0, 0, {
                    'name': line.product_id.name,
                    'product_id': line.product_id.id,
                    'product_uom_qty': 1.0,
                    'product_uom': line.product_id.uom_id.id,
                    'beneficiary_id': ben.id,
                    'location_id': source_location.id,
                    'location_dest_id': dest_location.id,
                }))

            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
                'project_id': self.campaign_id.id,
                'distribution_type': 'individual',
                'ai_suggestion': True,
                'move_ids': move_vals,
            })
            
            # Confirm picking to move to 'waiting' or 'assigned' state
            picking.action_confirm()
            pickings_created |= picking

            # Log audit
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'create',
                'target_model': 'stock.picking',
                'target_id': picking.id,
                'details': f"تم تطبيق اقتراح الذكاء الاصطناعي. تم إنشاء إذن التوزيع {picking.name} للحملة: {self.campaign_id.name}، الصنف: {line.product_id.name}، عدد المستفيدين: {len(line.beneficiary_ids)}",
            })

        # Return list action of created pickings
        return {
            'name': _('Created Distributions'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'list,form',
            'domain': [('id', 'in', pickings_created.ids)],
            'target': 'current',
        }


class KserAiSuggestionLine(models.TransientModel):
    _name = 'kser.ai.suggestion.line'
    _description = 'AI suggestion line'

    wizard_id = fields.Many2one(
        'kser.ai.wizard',
        string='Wizard',
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
    )
    beneficiary_ids = fields.Many2many(
        'kser.beneficiary',
        string='Beneficiaries',
    )
    priority = fields.Selection(
        [
            ('normal', 'Normal'),
            ('medium', 'Medium'),
            ('urgent', 'Urgent'),
        ],
        string='Priority',
    )
    rationale = fields.Text(
        string='Rationale',
    )
    approved = fields.Boolean(
        string='Approved?',
        default=True,
    )
