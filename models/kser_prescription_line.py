from odoo import models, fields

class KserPrescriptionLine(models.Model):
    _name = 'kser.prescription.line'
    _description = 'Prescription Line'

    prescription_id = fields.Many2one(
        'kser.prescription',
        string='Prescription',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one(
        'product.product',
        string='Medicine',
        required=True,
    )
    qty = fields.Float(
        string='Quantity',
        default=1.0,
        required=True,
    )
    instructions = fields.Char(
        string='Instructions',
    )
