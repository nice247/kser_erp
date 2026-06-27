from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class KserBeneficiary(models.Model):
    _name = 'kser.beneficiary'
    _description = 'Beneficiary'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'partner_id'
    _sql_constraints = [
        ('partner_id_unique', 'UNIQUE(partner_id)', 'This contact is already linked to another beneficiary!'),
        ('national_id_unique', 'UNIQUE(national_id_number)', 'This National ID is already registered!'),
    ]

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
        required=True,
        tracking=True,
    )
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
        required=True,
    )
    profession = fields.Char(
        string='Profession',
        size=100,
    )
    marital_status = fields.Selection(
        [
            ('single', 'Single'),
            ('married', 'Married'),
            ('widowed', 'Widowed'),
            ('divorced', 'Divorced'),
        ],
        string='Marital Status',
    )
    family_size = fields.Integer(
        string='Family Size',
        required=True,
        default=1,
    )
    health_conditions = fields.Text(
        string='Chronic Diseases',
    )
    birthdate = fields.Date(
        string='Birth Date',
    )
    district = fields.Char(
        string='District',
        size=100,
        required=True,
        index=True,
    )
    registration_date = fields.Date(
        string='Registration Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    is_verified = fields.Boolean(
        string='Is Verified?',
        default=False,
        index=True,
        tracking=True,
    )
    ocr_confidence = fields.Float(
        string='OCR Confidence',
    )
    priority_score = fields.Integer(
        string='Priority Score',
        compute='_compute_priority',
        store=True,
    )
    priority_level = fields.Selection(
        [
            ('normal', 'Normal'),
            ('medium', 'Medium'),
            ('urgent', 'Urgent'),
        ],
        string='Priority Level',
        compute='_compute_priority',
        store=True,
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='Head of Family',
        index=True,
        ondelete='set null',
    )
    registered_by = fields.Many2one(
        'res.users',
        string='Registered By',
        default=lambda self: self.env.uid,
    )

    @api.depends('health_conditions', 'marital_status', 'family_size', 'birthdate')
    def _compute_priority(self):
        today = fields.Date.today()
        for rec in self:
            score = 0

            if rec.health_conditions:
                score += 30

            if rec.marital_status in ('widowed', 'divorced'):
                score += 20

            if rec.family_size > 3:
                score += (rec.family_size - 3) * 5

            if rec.birthdate:
                age = relativedelta(today, rec.birthdate).years
                if age >= 60:
                    score += 15

            rec.priority_score = min(score, 100)

            if rec.priority_score >= 80:
                rec.priority_level = 'urgent'
            elif rec.priority_score >= 50:
                rec.priority_level = 'medium'
            else:
                rec.priority_level = 'normal'

    @api.constrains('family_size')
    def _check_family_size(self):
        for rec in self:
            if rec.family_size < 1:
                raise ValidationError(_('Family size must be greater than zero!'))

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError(_('OCR confidence must be between 0 and 1!'))
