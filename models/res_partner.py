from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'
    _sql_constraints = [
        ('kser_national_id_unique', 'UNIQUE(national_id_number)',
         'الرقم الوطني مسجل مسبقاً لمتطوع آخر!'),
    ]

    category_tag = fields.Many2one(
        'res.partner.category',
        string='تصنيف جهة الاتصال',
        index=True,
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='المشرف الميداني',
        index=True,
    )
    national_id_number = fields.Char(
        string='الرقم الوطني',
        size=20,
    )
    national_id_image = fields.Binary(
        string='صورة الهوية',
        attachment=True,
    )
