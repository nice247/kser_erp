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
        user = self.env.user
        is_admin = user.has_group('kser_erp.group_system_admin')

        for rec in self:
            # 1. User Role Constraints (Bypassed for System Admins)
            if not is_admin:
                if user.has_group('kser_erp.group_field_supervisor') or user.has_group('kser_erp.group_admin_supervisor'):
                    raise UserError(_("لا يمكن للمشرف الميداني أو المشرف الإداري تصديق أذونات الصرف والوارد مخزنياً!"))
                
                if user.has_group('kser_erp.group_doctor') or user.has_group('kser_erp.group_clinic_manager'):
                    raise UserError(_("لا يمكن للأطباء أو مشرفي العيادات تصديق أذونات الصرف والوارد مخزنياً!"))

                if user.has_group('kser_erp.group_stock_manager'):
                    if any(line.product_id.is_therapeutic for line in rec.move_ids_without_package):
                        raise UserError(_("لا يمكن لمسؤول المخازن تصديق صرف المنتجات العلاجية! هذا من صلاحيات الصيدلي فقط."))

            # 2. Pharmacist specific rules
            if user.has_group('kser_erp.group_pharmacist') and not is_admin:
                if rec.picking_type_id.code != 'outgoing':
                    raise UserError(_("الصيدلي لا يمكنه استلام مخزون (الوارد). يمكنك فقط اعتماد أذونات الصرف (المنصرف)."))
                for line in rec.move_ids_without_package:
                    if not line.product_id.is_therapeutic:
                        raise UserError(_("الصيدلي لا يمكنه صرف أو التعامل مع منتجات غير علاجية! المنتج (%s) غير علاجي.") % line.product_id.display_name)

            # 3. Campaign & Beneficiary Validation
            if rec.project_id and rec.project_id.state != 'approved':
                raise UserError(_("لا يمكن تأكيد التحويل. ميزانية الحملة '%s' غير معتمدة!") % rec.project_id.name)
            if rec.distribution_type == 'individual' and rec.partner_id and rec.partner_id.is_clinic_only:
                raise UserError(_("لا يمكن صرف إغاثة لمستفيد مسجل كـ 'عيادة فقط' دون رقم وطني وصورة هوية معتمدة!"))

            # 4. Single distribution per family in one campaign (Relief only)
            if rec.picking_type_id.code == 'outgoing' and rec.project_id and not rec.prescriber_id and rec.partner_id:
                beneficiary = self.env['kser.beneficiary'].sudo().search([('partner_id', '=', rec.partner_id.id)], limit=1)
                if beneficiary:
                    head = beneficiary.head_of_family_id or beneficiary
                    family_members = self.env['kser.beneficiary'].sudo().search([('head_of_family_id', '=', head.id)])
                    family_partner_ids = family_members.mapped('partner_id').ids
                    
                    duplicate_pickings = self.env['stock.picking'].sudo().search([
                        ('project_id', '=', rec.project_id.id),
                        ('state', '=', 'done'),
                        ('partner_id', 'in', family_partner_ids),
                        ('id', '!=', rec.id),
                        ('prescriber_id', '=', False),
                    ])
                    if duplicate_pickings:
                        raise UserError(_("لا يمكن صرف إغاثة لهذه الأسرة. لقد تم الصرف بالفعل لأحد أفراد الأسرة (%s) في هذه الحملة (%s)!") % (duplicate_pickings[0].partner_id.name, rec.project_id.name))
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
