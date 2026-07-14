from odoo import models, fields, api, _
from odoo.exceptions import UserError

class KserPrescription(models.Model):
    _name = 'kser.prescription'
    _description = 'Medical Prescription'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Prescription Ref',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Beneficiary',
        required=True,
        tracking=True,
    )
    doctor_id = fields.Many2one(
        'res.users',
        string='Doctor',
        required=True,
        default=lambda self: self.env.user,
        tracking=True,
    )
    prescription_date = fields.Date(
        string='Prescription Date',
        required=True,
        default=fields.Date.context_today,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('prescribed', 'Prescribed'),
        ('dispensed', 'Dispensed'),
    ], string='Status', default='draft', tracking=True)

    is_chronic = fields.Boolean(
        string='أمراض مزمنة',
        default=False,
        tracking=True,
    )
    allowed_dispense_count = fields.Integer(
        string='عدد مرات الصرف المسموحة',
        default=1,
        tracking=True,
    )
    dispensed_count = fields.Integer(
        string='عدد مرات الصرف الفعلية',
        default=0,
        readonly=True,
        tracking=True,
    )

    line_ids = fields.One2many(
        'kser.prescription.line',
        'prescription_id',
        string='Prescription Lines',
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Picking',
        readonly=True,
    )
    visit_id = fields.Many2one(
        'kser.clinic.visit',
        string='Clinic Visit',
        tracking=True,
    )
    followup_id = fields.Many2one(
        'kser.child.followup',
        string='Malnutrition Follow-up',
        tracking=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('kser.prescription') or _('New')
        return super().create(vals_list)

    def _create_stock_picking(self):
        self.ensure_one()
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'outgoing'),
            ('warehouse_id', '!=', False),
        ], limit=1)
        if not picking_type:
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'outgoing'),
            ], limit=1)

        if not picking_type:
            raise UserError(_("لم يتم العثور على نوع عملية التوزيع (شحنات صادرة)."))

        source_location = picking_type.default_location_src_id
        dest_location = picking_type.default_location_dest_id or self.env.ref('stock.stock_location_customers')

        if not source_location:
            raise UserError(_("لم يتم تهيئة موقع المصدر الافتراضي لنوع عملية التوزيع."))

        move_vals = []
        for line in self.line_ids:
            move_vals.append((0, 0, {
                'name': line.product_id.name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_id.uom_id.id,
                'beneficiary_id': self.beneficiary_id.id,
                'location_id': source_location.id,
                'location_dest_id': dest_location.id,
            }))

        picking = self.env['stock.picking'].sudo().create({
            'picking_type_id': picking_type.id,
            'location_id': source_location.id,
            'location_dest_id': dest_location.id,
            'partner_id': self.beneficiary_id.partner_id.id,
            'distribution_type': 'individual',
            'prescriber_id': self.doctor_id.id,
            'prescription_id': self.id,
            'move_ids': move_vals,
        })
        picking.sudo().action_confirm()

        self.sudo().write({
            'picking_id': picking.id,
        })
        return picking

    def action_confirm(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_('يمكن فقط تأكيد الروشتات في حالة المسودة!'))
            if not rec.line_ids:
                raise UserError(_('لا يمكن تأكيد روشتة فارغة!'))
            rec.write({'state': 'prescribed'})
            # إنشاء إذن الصرف (مستند التسليم) تلقائياً
            rec.sudo()._create_stock_picking()

    def action_dispense(self):
        self.ensure_one()
        if self.state == 'draft':
            raise UserError(_('يجب تأكيد الروشتة من الطبيب أولاً قبل الصرف!'))
        if self.state == 'dispensed':
            raise UserError(_('تم صرف هذه الروشتة بالكامل بالفعل!'))
        if not self.line_ids:
            raise UserError(_('لا يمكن صرف روشتة فارغة!'))

        # التحقق من وجود أذونات صرف مسودة أو مسندة نشطة لهذه الروشتة
        draft_pickings = self.env['stock.picking'].search([
            ('prescription_id', '=', self.id),
            ('state', 'not in', ['done', 'cancel']),
        ])
        if draft_pickings:
            # التوجيه إلى نموذج إذن الصرف الحالي ليتمكن الصيدلي من اعتماده
            return {
                'name': _('Dispensation Distribution'),
                'type': 'ir.actions.act_window',
                'res_model': 'stock.picking',
                'view_mode': 'form',
                'res_id': draft_pickings[0].id,
                'target': 'current',
            }

        # تطبيق قيود وحدود الصرف
        if self.is_chronic:
            current_year = fields.Date.today().year
            current_month = fields.Date.today().month
            existing_pickings = self.env['stock.picking'].search([
                ('prescription_id', '=', self.id),
                ('state', '=', 'done'),
            ])
            for p in existing_pickings:
                p_date = p.date_done or p.write_date
                if p_date and p_date.year == current_year and p_date.month == current_month:
                    raise UserError(_("تم صرف هذه الروشتة المزمنة لهذا الشهر بالفعل! تاريخ الصرف السابق: %s") % p_date.strftime('%Y-%m-%d'))
        else:
            if self.dispensed_count >= self.allowed_dispense_count:
                raise UserError(_("تم استنفاد عدد مرات الصرف المسموحة لهذه الروشتة (%s/%s)!") % (self.dispensed_count, self.allowed_dispense_count))

        # إذا لم يكن هناك إذن صرف مسبق (مثل روشتة الأمراض المزمنة في شهر جديد)، يتم إنشاء إذن جديد
        picking = self._create_stock_picking()

        self.env['kser.audit.log'].sudo().create({
            'action_type': 'approve',
            'target_model': 'kser.prescription',
            'target_id': self.id,
            'details': f"تم صرف الروشتة {self.name} للمستفيد {self.beneficiary_id.partner_id.name}. إذن الصرف: {picking.name}",
        })

        return {
            'name': _('Dispensation Distribution'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': picking.id,
            'target': 'current',
        }
