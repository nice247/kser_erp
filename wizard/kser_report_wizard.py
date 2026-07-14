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
        ('clinic', 'تقرير أداء العيادة'),
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
    notes = fields.Text(string='ملاحظات التقرير')
    preview_html = fields.Html(string='معاينة البيانات', readonly=True)

    def action_load_preview(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('تاريخ البداية يجب أن يكون قبل تاريخ النهاية!'))

        html = ""
        # 1. تشغيل منطق الاستعلام بناءً على نوع التقرير (self.report_type)
        if self.report_type == 'volunteers':
            res = self.env['report.kser_erp.report_volunteer_template']._get_report_values([], {'date_from': self.date_from, 'date_to': self.date_to})
            vols = res.get('volunteers', [])
            html = f"""
            <div style="font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; padding: 15px; background: #ffffff; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h3 style="color: #0E5E3A; border-bottom: 2px solid #0E5E3A; padding-bottom: 5px; margin-bottom: 15px;">📊 معاينة تقرير إنجاز المتطوعين</h3>
                <div style="display: flex; gap: 20px; margin-bottom: 15px;">
                    <div style="flex: 1; padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 12px; color: #666;">إجمالي المتطوعين النشطين</span>
                        <h2 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('total_volunteers', 0)}</h2>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 12px; color: #666;">إجمالي المهام المكتملة</span>
                        <h2 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('total_completed_tasks', 0)}</h2>
                    </div>
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <thead>
                        <tr style="background-color: #0E5E3A; color: white;">
                            <th style="padding: 8px; border: 1px solid #ddd;">الاسم</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">ساعات التطوع</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">المهام المكتملة</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">نسبة الإنجاز</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">إجمالي الحوافز</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            for v in vols[:5]:
                html += f"""
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd;">{v['name']}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{v['total_hours']}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{v['completed_tasks']}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{v['avg_completion_rate']}%</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{v['total_incentives']:,} ج.س</td>
                        </tr>
                """
            if len(vols) > 5:
                html += f"""
                        <tr>
                            <td colspan="5" style="padding: 8px; text-align: center; color: #888; font-style: italic;">... و {len(vols) - 5} متطوعين آخرين</td>
                        </tr>
                """
            if not vols:
                html += """
                        <tr>
                            <td colspan="5" style="padding: 8px; text-align: center; color: #888;">لا توجد بيانات متوفرة للفترة المحددة</td>
                        </tr>
                """
            html += """
                    </tbody>
                </table>
            </div>
            """
        elif self.report_type == 'performance':
            res = self.env['report.kser_erp.report_performance_template']._get_report_values([], {'date_from': self.date_from, 'date_to': self.date_to})
            stats = res.get('stats', {})
            html = f"""
            <div style="font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; padding: 15px; background: #ffffff; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h3 style="color: #0E5E3A; border-bottom: 2px solid #0E5E3A; padding-bottom: 5px; margin-bottom: 15px;">📊 معاينة تقرير أداء الغرفة وحجم المساعدات</h3>
                <div style="display: flex; gap: 20px; margin-bottom: 15px;">
                    <div style="flex: 1; padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 12px; color: #666;">إجمالي الكميات الموزعة</span>
                        <h2 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('total_quantity', 0):,}</h2>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 12px; color: #666;">إجمالي المستفيدين (أفراد)</span>
                        <h2 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('total_beneficiaries', 0)}</h2>
                    </div>
                </div>
                <table style="width: 100%; border-collapse: collapse; font-size: 12px;">
                    <thead>
                        <tr style="background-color: #0E5E3A; color: white;">
                            <th style="padding: 8px; border: 1px solid #ddd;">نوع المستفيد</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">ذكور</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">إناث</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">الإجمالي</th>
                            <th style="padding: 8px; border: 1px solid #ddd; text-align: center;">النسبة</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">أرامل</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('needy', {}).get('male', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('needy', {}).get('female', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{stats.get('needy', {}).get('total', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('needy', {}).get('pct', 0.0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">مرضى</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('patients', {}).get('male', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('patients', {}).get('female', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{stats.get('patients', {}).get('total', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('patients', {}).get('pct', 0.0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">كبار السن</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('elderly', {}).get('male', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('elderly', {}).get('female', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{stats.get('elderly', {}).get('total', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('elderly', {}).get('pct', 0.0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">أيتام</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('orphans', {}).get('male', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('orphans', {}).get('female', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{stats.get('orphans', {}).get('total', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('orphans', {}).get('pct', 0.0):.1f}%</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border: 1px solid #ddd; font-weight: bold;">أخرى</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('others', {}).get('male', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('others', {}).get('female', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center; font-weight: bold;">{stats.get('others', {}).get('total', 0)}</td>
                            <td style="padding: 8px; border: 1px solid #ddd; text-align: center;">{stats.get('others', {}).get('pct', 0.0):.1f}%</td>
                        </tr>
                    </tbody>
                </table>
            </div>
            """
        elif self.report_type == 'budget':
            res = self.env['report.kser_erp.report_budget_template']._get_report_values([], {'date_from': self.date_from, 'date_to': self.date_to})
            html = f"""
            <div style="font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; padding: 15px; background: #ffffff; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h3 style="color: #0E5E3A; border-bottom: 2px solid #0E5E3A; padding-bottom: 5px; margin-bottom: 15px;">📊 معاينة تقرير الميزانية التشغيلية</h3>
                <div style="display: flex; gap: 15px; margin-bottom: 15px;">
                    <div style="flex: 1; padding: 10px; background: #fcfcfc; border-radius: 6px; border-left: 4px solid #666;">
                        <span style="font-size: 11px; color: #666;">الرصيد الافتتاحي</span>
                        <h3 style="margin: 5px 0 0 0; color: #333;">{res.get('opening_balance', 0.0):,} ج.س</h3>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 11px; color: #666;">إجمالي الإيرادات (+)</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('total_revenues', 0.0):,} ج.س</h3>
                    </div>
                    <div style="flex: 1; padding: 10px; background: #fff5f5; border-radius: 6px; border-left: 4px solid #d9534f;">
                        <span style="font-size: 11px; color: #666;">إجمالي المصروفات (-)</span>
                        <h3 style="margin: 5px 0 0 0; color: #d9534f;">{res.get('total_expenses', 0.0):,} ج.س</h3>
                    </div>
                </div>
                <div style="padding: 12px; background: #E8F1EC; border-radius: 6px; text-align: center; border: 1px solid #0E5E3A;">
                    <span style="font-size: 13px; font-weight: bold; color: #0E5E3A;">صافي الرصيد المتبقي :</span>
                    <span style="font-size: 18px; font-weight: bold; color: #0E5E3A; margin-right: 10px;">{res.get('net_balance', 0.0):,} ج.س</span>
                </div>
            </div>
            """
        elif self.report_type == 'clinic':
            res = self.env['report.kser_erp.report_clinic_template']._get_report_values([], {'date_from': self.date_from, 'date_to': self.date_to})
            html = f"""
            <div style="font-family: 'Cairo', sans-serif; direction: rtl; text-align: right; padding: 15px; background: #ffffff; border-radius: 8px; border: 1px solid #e0e0e0; box-shadow: 0 4px 6px rgba(0,0,0,0.05);">
                <h3 style="color: #0E5E3A; border-bottom: 2px solid #0E5E3A; padding-bottom: 5px; margin-bottom: 15px;">📊 معاينة تقرير أداء العيادة</h3>
                <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin-bottom: 15px;">
                    <div style="padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 11px; color: #666;">المرضى الجدد</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('new_patients_count', 0)}</h3>
                    </div>
                    <div style="padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 11px; color: #666;">عدد الزيارات</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('visits_count', 0)}</h3>
                    </div>
                    <div style="padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 11px; color: #666;">الروشتات المكتوبة</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('prescriptions_count', 0)}</h3>
                    </div>
                    <div style="padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A;">
                        <span style="font-size: 11px; color: #666;">الأدوية المصروفة</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('dispensed_medicines_count', 0)}</h3>
                    </div>
                    <div style="padding: 10px; background: #f4f9f6; border-radius: 6px; border-left: 4px solid #0E5E3A; grid-column: span 2;">
                        <span style="font-size: 11px; color: #666;">الأطفال تحت المتابعة النشطة (سوء تغذية)</span>
                        <h3 style="margin: 5px 0 0 0; color: #0E5E3A;">{res.get('malnourished_children_count', 0)} أطفال</h3>
                    </div>
                </div>
            </div>
            """

        self.preview_html = html
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'kser.report.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_print_report(self):
        self.ensure_one()
        if self.date_from > self.date_to:
            raise UserError(_('تاريخ البداية يجب أن يكون قبل تاريخ النهاية!'))

        data = {
            'date_from': str(self.date_from),
            'date_to': str(self.date_to),
            'opening_balance': self.opening_balance,
            'notes': self.notes or '',
        }

        report_map = {
            'volunteers': 'kser_erp.report_kser_volunteers_achievement',
            'performance': 'kser_erp.report_kser_room_performance',
            'budget': 'kser_erp.report_kser_operational_budget',
            'clinic': 'kser_erp.report_kser_clinic_performance',
        }

        report_ref = report_map.get(self.report_type)
        return self.env.ref(report_ref).report_action(self, data=data)
