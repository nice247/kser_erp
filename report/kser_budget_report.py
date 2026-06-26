from odoo import models, fields, api


class KserBudgetReport(models.AbstractModel):
    _name = 'report.kser_erp.report_budget_template'
    _description = 'تقرير الميزانية التشغيلية'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        date_from = data.get('date_from', fields.Date.today().replace(month=1, day=1))
        date_to = data.get('date_to', fields.Date.today())
        opening_balance = data.get('opening_balance', 0.0)

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        revenues = self._compute_revenues(date_from, date_to)
        expenses = self._compute_expenses(date_from, date_to)

        total_revenues = sum(revenues.values())
        total_expenses = sum(expenses.values())
        net_balance = opening_balance + total_revenues - total_expenses

        return {
            'doc_ids': docids,
            'doc_model': 'account.move',
            'date_from': date_from,
            'date_to': date_to,
            'opening_balance': opening_balance,
            'revenues': revenues,
            'expenses': expenses,
            'total_revenues': total_revenues,
            'total_expenses': total_expenses,
            'net_balance': net_balance,
        }

    def _compute_revenues(self, date_from, date_to):
        revenues = {
            'تبرعات أفراد': 0.0,
            'تبرعات شركات': 0.0,
            'تبرعات حملات': 0.0,
            'إيرادات عيادة رمزية': 0.0,
        }

        donations = self.env['kser.cash.donation'].search([
            ('donation_date', '>=', date_from),
            ('donation_date', '<=', date_to),
        ])

        for donation in donations:
            if donation.campaign_id:
                revenues['تبرعات حملات'] += donation.amount
            else:
                revenues['تبرعات أفراد'] += donation.amount

        income_lines = self.env['account.move.line'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', ['income', 'income_other']),
        ])

        for line in income_lines:
            account_name = line.account_id.name or ''

            if 'عيادة' in account_name or 'رمزية' in account_name:
                revenues['إيرادات عيادة رمزية'] += line.credit - line.debit
            elif 'شركة' in account_name or 'مؤسسة' in account_name:
                revenues['تبرعات شركات'] += line.credit - line.debit

        return revenues

    def _compute_expenses(self, date_from, date_to):
        expenses = {
            'إيجار مستودعات': 0.0,
            'حوافز متطوعين': 0.0,
            'شراء مواد إغاثية': 0.0,
            'مصاريف تشغيلية أخرى': 0.0,
        }

        expense_lines = self.env['account.move.line'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'expense'),
        ])

        for line in expense_lines:
            account_name = line.account_id.name or ''
            amount = line.debit - line.credit

            if amount <= 0:
                continue

            if 'إيجار' in account_name or 'مستودع' in account_name:
                expenses['إيجار مستودعات'] += amount
            elif 'حوافز' in account_name or 'متطوع' in account_name:
                expenses['حوافز متطوعين'] += amount
            elif 'إغاث' in account_name or 'مواد' in account_name or 'شراء' in account_name:
                expenses['شراء مواد إغاثية'] += amount
            else:
                expenses['مصاريف تشغيلية أخرى'] += amount

        return expenses
