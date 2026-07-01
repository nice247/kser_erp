from odoo import models, fields, api

class KserChildFollowup(models.Model):
    _name = 'kser.child.followup'
    _description = 'Child Malnutrition Follow-up'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Child Beneficiary',
        required=True,
        domain="[('is_child', '=', True)]",
        tracking=True,
    )
    followup_date = fields.Date(
        string='Followup Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    weight = fields.Float(
        string='Weight (kg)',
        required=True,
        tracking=True,
    )
    height = fields.Float(
        string='Height (cm)',
        required=True,
        tracking=True,
    )
    nutrition_status = fields.Selection([
        ('severe', 'Severe Malnutrition'),
        ('moderate', 'Moderate Malnutrition'),
        ('normal', 'Normal / Recovered'),
    ], string='Nutrition Status', required=True, tracking=True)

    notes = fields.Text(
        string='Evaluation Notes',
    )
    measured_by = fields.Many2one(
        'res.users',
        string='Measured By',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    visit_id = fields.Many2one(
        'kser.clinic.visit',
        string='Clinic Visit',
        tracking=True,
    )
    next_visit_date = fields.Date(
        string='Next Visit Date',
        tracking=True,
    )
    visit_location = fields.Selection(
        [
            ('home', 'زيارة منزلية'),
            ('clinic', 'حضور للعيادة'),
        ],
        string='Visit Location',
        tracking=True,
    )
