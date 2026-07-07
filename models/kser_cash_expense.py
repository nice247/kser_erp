from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class KserCashExpense(models.Model):
    _name = 'kser.cash.expense'
    _description = 'Emergency Room Cash Expense'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='الرقم المرجعي',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    expense_type = fields.Selection([
        ('volunteer_incentive', 'حوافز متطوعين'),
        ('warehouse_rent', 'إيجار مستودعات'),
        ('relief_materials', 'شراء مواد إغاثية'),
        ('operational_expense', 'مصاريف تشغيلية أخرى'),
    ], string='نوع المصروف', required=True, tracking=True, default='operational_expense')

    campaign_id = fields.Many2one(
        'project.project',
        string='الحملة المرتبطة',
        required=True,
        tracking=True,
    )
    volunteer_id = fields.Many2one(
        'res.partner',
        string='المتطوع المستحق',
        tracking=True,
    )
    available_volunteer_ids = fields.Many2many(
        'res.partner',
        compute='_compute_available_volunteer_ids',
        string='المتطوعون المتاحون'
    )
    amount = fields.Monetary(
        string='المبلغ',
        required=True,
        currency_field='currency_id',
        tracking=True,
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='العملة',
        default=lambda self: self.env.company.currency_id.id,
        readonly=True,
    )
    date = fields.Date(
        string='تاريخ الصرف',
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    state = fields.Selection([
        ('draft', 'مسودة'),
        ('posted', 'معتمد ومصروف'),
    ], string='الحالة', default='draft', readonly=True, tracking=True)

    journal_id = fields.Many2one(
        'account.journal',
        string='دفتر اليومية (طريقة الدفع)',
        domain="[('type', 'in', ('bank', 'cash'))]",
        required=True,
        tracking=True,
        default=lambda self: self._default_journal_id(),
    )

    @api.model
    def _default_journal_id(self):
        # تفضيل دفتر البنك الرئيسي (رمز BNK) أو دفتر النقدية (رمز CASH)
        journal = self.env['account.journal'].search([
            ('code', 'in', ('BNK', 'CASH')),
            ('company_id', '=', self.env.company.id)
        ], order='type desc', limit=1)
        if not journal:
            journal = self.env['account.journal'].search([
                ('type', 'in', ('bank', 'cash')),
                ('company_id', '=', self.env.company.id)
            ], limit=1)
        return journal.id if journal else False

    move_id = fields.Many2one(
        'account.move',
        string='القيد المحاسبي المرتبط',
        ondelete='set null',
        readonly=True,
    )
    notes = fields.Text(string='ملاحظات وتفاصيل')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                seq = self.env['ir.sequence'].next_by_code('kser.cash.expense')
                if seq:
                    vals['name'] = seq
                else:
                    today = fields.Date.today()
                    year = today.strftime('%Y')
                    month = today.strftime('%m')
                    # البحث عن عدد المصروفات اليوم لإنشاء أرقام تسلسلية
                    exp_count = self.env['kser.cash.expense'].search_count([
                        ('date', '=', today)
                    ])
                    vals['name'] = f"EXP/{year}/{month}/{exp_count + 1:04d}"
        return super().create(vals_list)

    @api.constrains('amount')
    def _check_amount(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_('يجب أن يكون المبلغ أكبر من صفر!'))

    @api.constrains('expense_type', 'volunteer_id', 'campaign_id')
    def _check_volunteer_incentive(self):
        for rec in self:
            if rec.expense_type == 'volunteer_incentive':
                if not rec.volunteer_id:
                    raise ValidationError(_('يجب اختيار المتطوع عند صرف حافز متطوع!'))
                
                # البحث عن جميع المهام المسندة للمتطوع في الحملة
                all_tasks = self.env['project.task'].sudo().search([
                    ('project_id', '=', rec.campaign_id.id),
                    '|', ('volunteer_ids', 'in', [rec.volunteer_id.id]), ('user_ids.partner_id', '=', rec.volunteer_id.id)
                ])
                
                if not all_tasks:
                    raise ValidationError(_('لا يمكن صرف حافز للمتطوع %s لعدم وجود أي مهام مسندة إليه في حملة %s!') % (rec.volunteer_id.name, rec.campaign_id.name))
                
                completed_tasks = all_tasks.filtered(lambda t: t.stage_id.fold or t.state == '1_done' or t.completion_rate == 100.0)
                if not completed_tasks:
                    task_names = ", ".join(all_tasks.mapped('name'))
                    raise ValidationError(_('لا يمكن صرف حافز للمتطوع %s لعدم وجود مهام مكتملة له في حملة %s. المهام غير المكتملة هي: (%s)') % (rec.volunteer_id.name, rec.campaign_id.name, task_names))

    def action_confirm(self):
        """إنشاء قيد يومية محاسبي مباشرة لتسجيل المصروف."""
        if not (self.env.user.has_group('kser_erp.group_admin_supervisor') or self.env.user.has_group('kser_erp.group_system_admin')):
            raise ValidationError(_("غير مسموح باعتماد وصرف المصروفات إلا للمشرف الإداري!"))
            
        for rec in self:
            if rec.state != 'draft':
                continue
                
            if rec.campaign_id.state == 'draft':
                raise ValidationError(_("لا يمكن صرف هذا المصروف. ميزانية الحملة '%s' غير معتمدة بعد!") % rec.campaign_id.name)
            elif rec.campaign_id.state == 'done':
                raise ValidationError(_("لا يمكن صرف هذا المصروف. لقد تم إغلاق الحملة '%s' بالفعل!") % rec.campaign_id.name)
                
            if rec.expense_type == 'volunteer_incentive':
                rec._check_volunteer_incentive()

            journal = rec.journal_id
            if not journal:
                raise ValidationError(_("يرجى اختيار دفتر اليومية (طريقة الدفع) لتأكيد عملية الصرف."))
            
            if not journal.default_account_id:
                raise ValidationError(_("دفتر اليومية '%s' ليس لديه حساب افتراضي مهيأ.") % journal.name)

            account_code_map = {
                'volunteer_incentive': '52001',
                'warehouse_rent': '53001',
                'relief_materials': '13001',
                'operational_expense': '53009',
            }
            
            code = account_code_map.get(rec.expense_type, '53009')
            
            expense_account = self.env['account.account'].search([
                ('code', '=', code),
                ('company_ids', '=', self.env.company.id)
            ], limit=1)
            
            if not expense_account:
                expense_account = self.env['account.account'].search([
                    ('account_type', '=', 'expense'),
                    ('company_ids', '=', self.env.company.id)
                ], limit=1)
                
            if not expense_account:
                raise ValidationError(_("لم يتم العثور على حساب مصروف مناسب في شجرة الحسابات. يرجى تهيئة الحسابات أولاً."))

            label = _("Expense: %s for campaign %s") % (rec.get_expense_type_display(), rec.campaign_id.name)
            if rec.expense_type == 'volunteer_incentive':
                label = _("Volunteer Incentive: %s - campaign %s") % (rec.volunteer_id.name, rec.campaign_id.name)

            move_vals = {
                'move_type': 'entry',
                'date': rec.date,
                'journal_id': journal.id,
                'ref': rec.name,
                'line_ids': [
                    (0, 0, {
                        'name': label,
                        'account_id': expense_account.id,
                        'debit': rec.amount,
                        'credit': 0.0,
                        'partner_id': rec.volunteer_id.id if rec.volunteer_id else False,
                        'project_id': rec.campaign_id.id,
                    }),
                    (0, 0, {
                        'name': label,
                        'account_id': journal.default_account_id.id,
                        'debit': 0.0,
                        'credit': rec.amount,
                        'partner_id': rec.volunteer_id.id if rec.volunteer_id else False,
                        'project_id': rec.campaign_id.id,
                    }),
                ]
            }
            
            move = self.env['account.move'].create(move_vals)
            move.action_post()

            rec.write({
                'move_id': move.id,
                'state': 'posted',
            })
            
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'approve',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم اعتماد وصرف مصروف بقيمة: {rec.amount} ج.س. لنوع: {rec.get_expense_type_display()}. رقم القيد: {move.name}",
            })

    def get_expense_type_display(self):
        self.ensure_one()
        types = dict(self._fields['expense_type'].selection)
        return types.get(self.expense_type, self.expense_type)

    @api.depends('campaign_id')
    def _compute_available_volunteer_ids(self):
        for rec in self:
            if rec.campaign_id:
                # البحث عن جميع المهام الخاصة بالحملة
                tasks = self.env['project.task'].sudo().search([
                    ('project_id', '=', rec.campaign_id.id)
                ])
                # تجميع المتطوعين المسندين في الحقول المخصصة
                partners = tasks.mapped('volunteer_ids') | tasks.mapped('user_ids.partner_id')
                rec.available_volunteer_ids = partners
            else:
                rec.available_volunteer_ids = self.env['res.partner']

    @api.onchange('campaign_id')
    def _onchange_campaign_id(self):
        if self.campaign_id and self.volunteer_id:
            # التحقق مما إذا كان المتطوع الحالي يملك مهمة في الحملة الجديدة
            tasks = self.env['project.task'].sudo().search([
                ('project_id', '=', self.campaign_id.id),
                '|', ('volunteer_ids', 'in', [self.volunteer_id.id]), ('user_ids.partner_id', '=', self.volunteer_id.id)
            ], limit=1)
            if not tasks:
                self.volunteer_id = False
