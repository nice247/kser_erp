from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kser_gemini_api_key = fields.Char(
        string='مفتاح الذكاء الاصطناعي',
        config_parameter='kser.gemini_api_key',
    )
