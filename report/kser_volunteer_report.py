from odoo import models, fields, api


class KserVolunteerReport(models.AbstractModel):
    _name = 'report.kser_erp.report_volunteer_template'
    _description = 'تقرير إنجاز المتطوعين الميدانيين'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        date_from = data.get('date_from', fields.Date.today().replace(month=1, day=1))
        date_to = data.get('date_to', fields.Date.today())

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        done_tasks = self.env['project.task'].search([
            ('stage_id.fold', '=', True),
            ('date_deadline', '>=', date_from),
            ('date_deadline', '<=', date_to),
        ])

        volunteer_map = {}

        for task in done_tasks:
            assignees = task.user_ids
            if not assignees:
                continue

            for user in assignees:
                partner = user.partner_id
                vol_id = partner.id

                if vol_id not in volunteer_map:
                    volunteer_map[vol_id] = {
                        'name': partner.name,
                        'national_id': partner.national_id_number or '-',
                        'completed_tasks': 0,
                        'completion_rates': [],
                        'campaign_ids': set(),
                        'total_hours': 0.0,
                        'total_incentives': 0.0,
                    }

                volunteer_map[vol_id]['completed_tasks'] += 1

                if task.completion_rate:
                    volunteer_map[vol_id]['completion_rates'].append(task.completion_rate)

                if task.project_id:
                    volunteer_map[vol_id]['campaign_ids'].add(task.project_id.id)

        incentive_lines = self.env['account.move.line'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('parent_state', '=', 'posted'),
            ('account_id.account_type', '=', 'expense'),
        ])

        incentive_map = {}
        for line in incentive_lines:
            account_name = line.account_id.name or ''
            if 'حوافز' not in account_name and 'متطوع' not in account_name:
                continue
            if line.partner_id:
                pid = line.partner_id.id
                incentive_map.setdefault(pid, 0.0)
                incentive_map[pid] += line.debit - line.credit

        timesheet_lines = self.env['account.analytic.line'].search([
            ('date', '>=', date_from),
            ('date', '<=', date_to),
            ('project_id', '!=', False),
        ])

        hours_map = {}
        for ts in timesheet_lines:
            if ts.user_id and ts.user_id.partner_id:
                pid = ts.user_id.partner_id.id
                hours_map.setdefault(pid, 0.0)
                hours_map[pid] += ts.unit_amount or 0.0

        volunteers_list = []
        for vol_id, vol_data in volunteer_map.items():
            rates = vol_data['completion_rates']
            avg_rate = sum(rates) / len(rates) if rates else 0.0

            raw_incentive = incentive_map.get(vol_id, 0.0)
            if not vol_data['campaign_ids']:
                raw_incentive = 0.0

            vol_data['avg_completion_rate'] = round(avg_rate, 2)
            vol_data['total_hours'] = round(hours_map.get(vol_id, 0.0), 2)
            vol_data['total_incentives'] = round(raw_incentive, 2)
            vol_data['campaign_count'] = len(vol_data['campaign_ids'])

            del vol_data['completion_rates']
            del vol_data['campaign_ids']

            volunteers_list.append(vol_data)

        volunteers_list.sort(
            key=lambda v: (v['completed_tasks'], v['avg_completion_rate']),
            reverse=True,
        )

        return {
            'doc_ids': docids,
            'doc_model': 'project.task',
            'date_from': date_from,
            'date_to': date_to,
            'volunteers': volunteers_list,
            'total_volunteers': len(volunteers_list),
            'total_completed_tasks': sum(v['completed_tasks'] for v in volunteers_list),
        }
