from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    kser_ai_provider = fields.Selection([
        ('gemini', 'Google Gemini'),
        ('ollama', 'Local LLM (Ollama)')
    ], string='مزود الذكاء الاصطناعي', config_parameter='kser.ai_provider', default='gemini')

    kser_ai_api_key = fields.Char(
        string='مفتاح الذكاء الاصطناعي',
        config_parameter='kser.ai_api_key',
    )

    kser_local_llm_url = fields.Char(
        string='رابط الخادم المحلي',
        config_parameter='kser.local_llm_url',
        default='http://localhost:11434/api/generate',
    )

    kser_ai_model = fields.Char(
        string='اسم النموذج',
        config_parameter='kser.ai_model',
        default='gemini-2.5-flash',
    )
