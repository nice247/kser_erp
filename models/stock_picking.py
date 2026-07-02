from odoo import models, fields, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    project_id = fields.Many2one(
        'project.project',
        string='Campaign (Project)',
        index=True,
        tracking=True,
    )
    distribution_type = fields.Selection(
        [
            ('individual', 'Specific Beneficiary'),
            ('campaign', 'Campaign'),
            ('group', 'Group'),
        ],
        string='Distribution Type',
        index=True,
    )
    ai_suggestion = fields.Boolean(
        string='AI Suggestion?',
        default=False,
        index=True,
    )
    prescriber_id = fields.Many2one(
        'res.users',
        string='Prescriber Doctor',
        tracking=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        related='partner_id.national_id_number',
        readonly=True,
    )

    def button_validate(self):
        for rec in self:
            if rec.project_id and rec.project_id.state != 'approved':
                raise UserError(_("لا يمكن تأكيد التحويل. ميزانية الحملة '%s' غير معتمدة!") % rec.project_id.name)
            if rec.distribution_type == 'individual' and rec.partner_id and rec.partner_id.is_clinic_only:
                raise UserError(_("لا يمكن صرف إغاثة لمستفيد مسجل كـ 'عيادة فقط' دون رقم وطني وصورة هوية معتمدة!"))
        res = super().button_validate()
        for rec in self:
            if rec.state == 'done':
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'approve',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم تصديق إذن التوزيع {rec.name}. الحملة: {rec.project_id.name if rec.project_id else 'غير محدد'}",
                })
        return res
