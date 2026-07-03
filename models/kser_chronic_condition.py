from odoo import models, fields

class KserChronicCondition(models.Model):
    _name = 'kser.chronic.condition'
    _description = 'Chronic Condition'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True)
