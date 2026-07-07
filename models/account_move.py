from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'

    def action_post(self):
        volunteer_tag = self.env.ref('kser_erp.partner_category_volunteer', raise_if_not_found=False)
        if volunteer_tag:
            for move in self:
                for line in move.line_ids:
                    if line.partner_id and line.partner_id.category_tag == volunteer_tag:
                        if line.account_id.account_type == 'expense':
                            account_name = line.account_id.name or ''
                            if any(w in account_name for w in ('حوافز', 'متطوع', 'Incentive', 'Volunteer')):
                                project = line.project_id
                                if project:
                                    completed_tasks = self.env['project.task'].search_count([
                                        ('project_id', '=', project.id),
                                        '|', ('volunteer_ids', 'in', [line.partner_id.id]), ('user_ids.partner_id', '=', line.partner_id.id),
                                        '|', '|', ('stage_id.fold', '=', True), ('state', '=', '1_done'), ('completion_rate', '=', 100.0)
                                    ])
                                    if completed_tasks == 0:
                                        raise ValidationError(_("لا يمكن صرف حافز للمتطوع %s في الحملة %s لأنه لا يملك أي مهمة مكتملة مرتبطة بها!") % (line.partner_id.name, project.name))
        return super().action_post()


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    project_id = fields.Many2one('project.project', string='المشروع/الحملة')

