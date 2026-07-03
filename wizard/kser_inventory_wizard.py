import logging
import requests

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class KserInventoryWizard(models.TransientModel):
    _name = 'kser.inventory.wizard'
    _description = 'Stock Gap Analysis Wizard'

    name = fields.Char(
        string='Name',
        default='فحص حالة المخزون',
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
        'kser.inventory.uncovered.case',
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
            'name': _('فحص حالة المخزون'),
            'res_model': 'kser.inventory.wizard',
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

        CONDITION_ACTIVE_INGREDIENT_MAP = {
            'diabetes': ['metformin', 'insulin', 'gliclazide', 'glimepiride', 'sitagliptin'],
            'hypertension': ['amlodipine', 'valsartan', 'losartan', 'lisinopril', 'bisoprolol'],
            'asthma': ['salbutamol', 'budesonide', 'fluticasone', 'formoterol'],
            'heart_disease': ['aspirin', 'clopidogrel', 'atorvastatin', 'rosuvastatin', 'digoxin'],
            'thyroid': ['levothyroxine', 'carbimazole'],
            'kidney_disease': ['furosemide', 'spironolactone'],
            'epilepsy': ['levetiracetam', 'valproate', 'carbamazepine'],
            'sickle_cell': ['hydroxyurea', 'folic acid'],
            'hepatitis_b': ['entecavir', 'tenofovir'],
        }

        quants = self.env['stock.quant'].search([
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ])

        inventory = {}
        for quant in quants:
            if quant.product_id.active_ingredient:
                ing = quant.product_id.active_ingredient.strip().lower()
                inventory[ing] = inventory.get(ing, 0) + quant.quantity

        total_beneficiaries_count = self.env['kser.beneficiary'].search_count([])

        beneficiaries_with_conds = self.env['kser.beneficiary'].search([
            ('health_conditions', '!=', False),
        ])

        all_conditions = self.env['kser.chronic.condition'].search([])
        code_name_map = {c.code: c.name for c in all_conditions}

        condition_demand = {}
        condition_supply = {}

        # 1. حساب الاحتياج (Demand) أولاً لجميع الحالات
        for ben in beneficiaries_with_conds:
            ben_condition_codes = ben.health_conditions.mapped('code')
            for cond_code in ben_condition_codes:
                if cond_code in CONDITION_ACTIVE_INGREDIENT_MAP:
                    cond_name = code_name_map.get(cond_code, cond_code)
                    condition_demand[cond_name] = condition_demand.get(cond_name, 0) + 1

        # 2. حساب المعروض (Supply) لكل حالة من المخزون
        for cond_code, meds in CONDITION_ACTIVE_INGREDIENT_MAP.items():
            cond_name = code_name_map.get(cond_code, cond_code)
            supply = sum(inventory.get(med, 0) for med in meds)
            condition_supply[cond_name] = supply

        uncovered_cases_data = []

        # 3. المرور مرة أخرى لتقييم كل مستفيد وبناء التبرير (Justification)
        for ben in beneficiaries_with_conds:
            ben_condition_codes = ben.health_conditions.mapped('code')
            
            for cond_code in ben_condition_codes:
                if cond_code in CONDITION_ACTIVE_INGREDIENT_MAP:
                    cond_name = code_name_map.get(cond_code, cond_code)
                    meds = CONDITION_ACTIVE_INGREDIENT_MAP[cond_code]
                    
                    demand = condition_demand.get(cond_name, 1)
                    supply = condition_supply.get(cond_name, 0)
                    coverage = supply / demand if demand > 0 else 0
                    coverage_pct = round(coverage * 100, 1)
                    meds_str = " أو ".join(meds).title()

                    # صياغة رسالة التبرير بناءً على حالة التغطية
                    if coverage >= 1:
                        status = "🟢 متوفر بالكامل (آمن)"
                        justification = f"المستفيد مصاب بـ ({cond_name}). المواد الفعالة ({meds_str}) مدرجة كعلاج معتمد لهذه الحالة. الكمية المتوفرة في المخزون: {int(supply)} عبوة، وعدد المستفيدين المصابين بنفس الحالة: {demand} مستفيد. حالة التغطية: {status} بنسبة {coverage_pct}%."
                    elif supply > 0:
                        status = "🟡 غير كافٍ (متوسط)"
                        justification = f"المستفيد مصاب بـ ({cond_name}). المواد الفعالة ({meds_str}) مدرجة كعلاج معتمد لهذه الحالة. الكمية المتوفرة في المخزون: {int(supply)} عبوة، بينما عدد المستفيدين المصابين بنفس الحالة: {demand} مستفيد. حالة التغطية: {status}، مما يعني وجود عجز (تغطية بنسبة {coverage_pct}% فقط)."
                    else:
                        status = "🔴 غير متوفر إطلاقاً (حرج)"
                        justification = f"المستفيد مصاب بـ ({cond_name}). المواد الفعالة ({meds_str}) مدرجة كعلاج معتمد. الكمية المتوفرة في المخزون: 0 عبوة، بينما عدد المستفيدين المصابين بنفس الحالة: {demand} مستفيد. حالة التغطية: {status} (نسبة التغطية 0%)."

                    # تسجيل الحالة إذا كانت غير مغطاة بالكامل (نسبة التغطية أقل من 1)
                    if coverage < 1:
                        uncovered_cases_data.append({
                            'beneficiary_id': ben.id,
                            'health_conditions': cond_name,
                            'needed_medicine': ", ".join(meds).title(),
                            'justification': justification,
                        })

        urgency_lines = []
        for cond_name, demand in condition_demand.items():
            supply = condition_supply.get(cond_name, 0)
            coverage = supply / demand if demand > 0 else 0
            status = "🔴 حرج (عجز)" if coverage < 1 else ("🟡 متوسط" if coverage < 2 else "🟢 آمن (متوفر)")
            urgency_lines.append(f"- {cond_name}: الاحتياج ({demand} مستفيد)، المتوفر ({int(supply)} عبوة) | الحالة: {status}")

        urgency_report = "تقرير الإلحاح ونسبة التغطية:\n" + "\n".join(urgency_lines) if urgency_lines else "لا توجد حالات صحية مسجلة حالياً لحساب الإلحاح والمطابقة."
        summary_text = f"تم فحص {total_beneficiaries_count} مستفيد إجمالاً. تم العثور على {len(uncovered_cases_data)} حالة احتياج غير مغطاة بالأدوية المطلوبة."

        self.uncovered_case_ids.unlink()

        for case in uncovered_cases_data:
            self.env['kser.inventory.uncovered.case'].create({
                'wizard_id': self.id,
                'beneficiary_id': case['beneficiary_id'],
                'health_conditions': case['health_conditions'],
                'needed_medicine': case['needed_medicine'],
                'justification': case['justification'],
            })

        self.write({
            'summary': summary_text,
            'urgency_report': urgency_report,
            'state': 'result',
        })

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'kser.inventory.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }


class KserInventoryUncoveredCase(models.TransientModel):
    _name = 'kser.inventory.uncovered.case'
    _description = 'AI Uncovered Case'

    wizard_id = fields.Many2one(
        'kser.inventory.wizard',
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
