from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'

    category_tag = fields.Many2one(
        'res.partner.category',
        string='تصنيف جهة الاتصال',
    )
    supervisor_id = fields.Many2one(
        'res.users',
        string='المشرف الميداني',
    )
    national_id_number = fields.Char(
        string='الرقم الوطني',
        size=20,
    )
    national_id_image = fields.Binary(
        string='صورة الهوية',
        attachment=True,
    )
