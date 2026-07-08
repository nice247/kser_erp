from odoo import models, fields, api


class KserVolunteerReport(models.AbstractModel):
    _name = 'report.kser_erp.report_volunteer_template'
    _description = 'Field Volunteers Performance Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        date_from = data.get('date_from', fields.Date.today().replace(month=1, day=1))
        date_to = data.get('date_to', fields.Date.today())

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        bot_partner = self.env.ref('base.partner_root', raise_if_not_found=False)
        bot_partner_id = bot_partner.id if bot_partner else None

        done_tasks = self.env['project.task'].search([
            '|', ('stage_id.fold', '=', True), ('state', '=', '1_done'),
        ])
        
        # تصفية المهام بناءً على الموعد النهائي أو تاريخ الكتابة خلال الفترة المحددة
        filtered_task_ids = []
        for task in done_tasks:
            task_date = task.date_deadline or task.write_date.date()
            if date_from <= task_date <= date_to:
                filtered_task_ids.append(task.id)
        done_tasks = self.env['project.task'].browse(filtered_task_ids)

        volunteer_map = {}

        for task in done_tasks:
            if task.task_volunteer_ids:
                for tv in task.task_volunteer_ids:
                    partner = tv.volunteer_id
                    if not partner or not partner.active or partner.name == 'OdooBot' or partner.id == bot_partner_id:
                        continue
                    vol_id = partner.id

                    if vol_id not in volunteer_map:
                        volunteer_map[vol_id] = {
                            'id': vol_id,
                            'name': partner.name,
                            'national_id': partner.national_id_number or '-',
                            'completed_tasks': 0,
                            'completion_rates': [],
                            'campaign_ids': set(),
                            'total_hours': 0.0,
                            'total_incentives': 0.0,
                        }

                    volunteer_map[vol_id]['completed_tasks'] += 1
                    volunteer_map[vol_id]['total_hours'] += tv.hours_worked

                    if tv.completion_rate:
                        volunteer_map[vol_id]['completion_rates'].append(tv.completion_rate)

                    if task.project_id:
                        volunteer_map[vol_id]['campaign_ids'].add(task.project_id.id)
            else:
                assignees = task.user_ids
                if not assignees:
                    continue

                for user in assignees:
                    partner = user.partner_id
                    if not partner or not partner.active or partner.name == 'OdooBot' or partner.id == bot_partner_id:
                        continue
                    vol_id = partner.id

                    if vol_id not in volunteer_map:
                        volunteer_map[vol_id] = {
                            'id': vol_id,
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
            if 'حوافز' not in account_name and 'متطوع' not in account_name and 'Incentive' not in account_name and 'Volunteer' not in account_name:
                continue
            if line.partner_id:
                pid = line.partner_id.id
                incentive_map.setdefault(pid, 0.0)
                incentive_map[pid] += line.debit - line.credit

        volunteers_list = []
        for vol_id, vol_data in volunteer_map.items():
            rates = vol_data['completion_rates']
            avg_rate = sum(rates) / len(rates) if rates else 0.0

            raw_incentive = incentive_map.get(vol_id, 0.0)
            if not vol_data['campaign_ids']:
                raw_incentive = 0.0

            vol_data['avg_completion_rate'] = round(avg_rate, 2)
            vol_data['total_hours'] = round(vol_data.get('total_hours', 0.0), 2)
            vol_data['total_incentives'] = round(raw_incentive, 2)
            vol_data['campaign_count'] = len(vol_data['campaign_ids'])

            del vol_data['completion_rates']
            del vol_data['campaign_ids']

            volunteers_list.append(vol_data)

        # الترتيب حسب: المهام المكتملة (أكبر أولاً)، متوسط نسبة الإنجاز (أكبر أولاً)، إجمالي الساعات (أكبر أولاً)، ورقم المعرف (الأقدم أولاً)
        volunteers_list.sort(
            key=lambda v: (v['completed_tasks'], v['avg_completion_rate'], v['total_hours'], -v['id']),
            reverse=True,
        )

        return {
            'doc_ids': docids,
            'doc_model': 'project.task',
            'company': self.env.company,
            'date_from': date_from,
            'date_to': date_to,
            'volunteers': volunteers_list,
            'total_volunteers': len(volunteers_list),
            'total_completed_tasks': sum(v['completed_tasks'] for v in volunteers_list),
        }
