from odoo import models, fields, api


class KserBudgetReport(models.AbstractModel):
    _name = 'report.kser_erp.report_budget_template'
    _description = 'Operating Budget Report'

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
            'company': self.env.company,
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
            'Individual Donations': 0.0,
            'Corporate Donations': 0.0,
            'Campaign Donations': 0.0,
            'Clinic Nominal Revenues': 0.0,
        }

        donations = self.env['kser.cash.donation'].search([
            ('donation_date', '>=', date_from),
            ('donation_date', '<=', date_to),
        ])

        for donation in donations:
            if donation.campaign_id:
                revenues['Campaign Donations'] += donation.amount
            else:
                revenues['Individual Donations'] += donation.amount

        income_lines = self.env['account.move.line'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', 'in', ['income', 'income_other']),
        ])

        for line in income_lines:
            account_name = line.account_id.name or ''

            if 'عيادة' in account_name or 'رمزية' in account_name or 'Clinic' in account_name:
                revenues['Clinic Nominal Revenues'] += line.credit - line.debit
            elif 'شركة' in account_name or 'مؤسسة' in account_name or 'Corporate' in account_name:
                revenues['Corporate Donations'] += line.credit - line.debit

        return revenues

    def _compute_expenses(self, date_from, date_to):
        expenses = {
            'Warehouse Rent': 0.0,
            'Volunteer Incentives': 0.0,
            'Relief Materials Purchases': 0.0,
            'Other Operational Expenses': 0.0,
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

            if 'إيجار' in account_name or 'مستودع' in account_name or 'Rent' in account_name:
                expenses['Warehouse Rent'] += amount
            elif 'حوافز' in account_name or 'متطوع' in account_name or 'Incentive' in account_name:
                expenses['Volunteer Incentives'] += amount
            elif 'إغاث' in account_name or 'مواد' in account_name or 'شراء' in account_name or 'Material' in account_name:
                expenses['Relief Materials Purchases'] += amount
            else:
                expenses['Other Operational Expenses'] += amount

        return expenses
