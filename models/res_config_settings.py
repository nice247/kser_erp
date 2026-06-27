from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kser_springboot_api_key = fields.Char(
        string='مفتاح API',
        config_parameter='kser.springboot_api_key',
    )
    kser_springboot_base_url = fields.Char(
        string='رابط الخادم (Base URL)',
        config_parameter='kser.springboot_base_url',
    )
