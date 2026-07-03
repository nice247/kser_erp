from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _register_hook(self):
        super()._register_hook()
        kser_group = self.env.ref('kser_erp.group_kser_user', raise_if_not_found=False)
        dashboard_action = self.env.ref('kser_erp.action_kser_emergency_dashboard', raise_if_not_found=False)
        if kser_group and dashboard_action:
            users = kser_group.sudo().users
            for user in users:
                if user.action_id != dashboard_action:
                    user.sudo().write({'action_id': dashboard_action.id})

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        kser_group = self.env.ref('kser_erp.group_kser_user', raise_if_not_found=False)
        dashboard_action = self.env.ref('kser_erp.action_kser_emergency_dashboard', raise_if_not_found=False)
        if kser_group and dashboard_action:
            for user in users:
                if kser_group in user.groups_id:
                    user.sudo().write({'action_id': dashboard_action.id})
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'groups_id' in vals:
            kser_group = self.env.ref('kser_erp.group_kser_user', raise_if_not_found=False)
            dashboard_action = self.env.ref('kser_erp.action_kser_emergency_dashboard', raise_if_not_found=False)
            if kser_group and dashboard_action:
                for user in self:
                    if kser_group in user.groups_id and user.action_id != dashboard_action:
                        user.sudo().write({'action_id': dashboard_action.id})
        return res
