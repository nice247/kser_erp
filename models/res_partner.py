from odoo import models, fields


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
    )
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
    )
