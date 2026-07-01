from odoo import models, fields, api, _

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
        ('dispensed', 'Dispensed'),
    ], string='Status', default='draft', tracking=True)

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('kser.prescription') or _('New')
        return super().create(vals_list)

    def action_dispense(self):
        self.ensure_one()
        if self.state == 'dispensed':
            raise UserError(_('تم صرف هذه الروشتة بالفعل!'))
        if not self.line_ids:
            raise UserError(_('لا يمكن صرف روشتة فارغة!'))

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
            'move_ids': move_vals,
        })
        picking.sudo().action_confirm()

        self.sudo().write({
            'state': 'dispensed',
            'picking_id': picking.id,
        })

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
