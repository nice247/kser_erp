from odoo import models, fields, api


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _register_hook(self):
        super()._register_hook()
        receptionist_group = self.env.ref('kser_erp.group_receptionist', raise_if_not_found=False)
        receptionist_action = self.env.ref('kser_erp.action_kser_clinic_visit_today', raise_if_not_found=False)
        if receptionist_group and receptionist_action:
            users = receptionist_group.sudo().users
            for user in users:
                if user.action_id != receptionist_action:
                    user.sudo().write({'action_id': receptionist_action.id})

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        receptionist_group = self.env.ref('kser_erp.group_receptionist', raise_if_not_found=False)
        receptionist_action = self.env.ref('kser_erp.action_kser_clinic_visit_today', raise_if_not_found=False)
        if receptionist_group and receptionist_action:
            for user in users:
                if receptionist_group in user.groups_id:
                    user.sudo().write({'action_id': receptionist_action.id})
        return users

    def write(self, vals):
        res = super().write(vals)
        if 'groups_id' in vals:
            receptionist_group = self.env.ref('kser_erp.group_receptionist', raise_if_not_found=False)
            receptionist_action = self.env.ref('kser_erp.action_kser_clinic_visit_today', raise_if_not_found=False)
            if receptionist_group and receptionist_action:
                for user in self:
                    if receptionist_group in user.groups_id and user.action_id != receptionist_action:
                        user.sudo().write({'action_id': receptionist_action.id})
        return res
