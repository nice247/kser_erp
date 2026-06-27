from odoo import models, fields, api, _


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _sql_constraints = [
        ('kser_national_id_unique', 'UNIQUE(national_id_number)',
         'This National ID is already registered to another volunteer!'),
    ]

    category_tag = fields.Many2one(
        'res.partner.category',
        string='Contact Category',
        index=True,
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='Field Supervisor',
        index=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
        required=True,
    )
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
        required=True,
    )

    task_ids = fields.One2many(
        'project.task',
        'volunteer_id',
        string='Volunteer Tasks',
    )
    donation_ids = fields.One2many(
        'kser.cash.donation',
        'partner_id',
        string='Donations',
    )

    task_count = fields.Integer(
        compute='_compute_task_count',
        string='Tasks Count',
    )
    donation_count = fields.Integer(
        compute='_compute_donation_count',
        string='Donations Count',
    )

    @api.depends('task_ids')
    def _compute_task_count(self):
        for rec in self:
            rec.task_count = len(rec.task_ids)

    @api.depends('donation_ids')
    def _compute_donation_count(self):
        for rec in self:
            rec.donation_count = len(rec.donation_ids)

    def action_view_tasks(self):
        self.ensure_one()
        return {
            'name': _('Assigned Tasks'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'list,form',
            'domain': [('volunteer_id', '=', self.id)],
            'context': {'default_volunteer_id': self.id},
        }

    def action_view_donations(self):
        self.ensure_one()
        return {
            'name': _('Donations'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.cash.donation',
            'view_mode': 'list,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {'default_partner_id': self.id},
        }
