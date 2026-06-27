# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class KserReportWizard(models.TransientModel):
    _name = 'kser.report.wizard'
    _description = 'KSER Report Generation Wizard'

    report_type = fields.Selection([
        ('volunteers', 'تقرير إنجاز المتطوعين الميدانيين'),
        ('performance', 'تقرير أداء الغرفة وحجم المساعدات'),
        ('budget', 'تقرير الميزانية التشغيلية'),
    ], string='نوع التقرير', required=True, default='volunteers')

    date_from = fields.Date(
        string='من تاريخ',
        required=True,
        default=lambda self: fields.Date.today().replace(month=1, day=1),
    )
    date_to = fields.Date(
        string='إلى تاريخ',
        required=True,
        default=fields.Date.today,
    )
    opening_balance = fields.Float(
        string='الرصيد الافتتاحي (ج.س)',
        default=0.0,
        help='يُستخدم فقط في تقرير الميزانية التشغيلية',
    )

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('تاريخ البداية يجب أن يكون قبل تاريخ النهاية!'))

        data = {
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'opening_balance': self.opening_balance,
        }

        report_map = {
            'volunteers': 'kser_erp.report_kser_volunteers_achievement',
            'performance': 'kser_erp.report_kser_room_performance',
            'budget': 'kser_erp.report_kser_operational_budget',
        }

        report_ref = report_map.get(self.report_type)
        return self.env.ref(report_ref).report_action(self, data=data)
