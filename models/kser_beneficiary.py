from dateutil.relativedelta import relativedelta

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools.translate import _


class KserBeneficiary(models.Model):
    _name = 'kser.beneficiary'
    _description = 'Beneficiary'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'partner_id'
    _sql_constraints = [
        ('partner_id_unique', 'UNIQUE(partner_id)', 'جهة الاتصال هذه مرتبطة بالفعل بمستفيد آخر!'),
        ('national_id_unique', 'UNIQUE(national_id_number)', 'الرقم الوطني هذا مسجل بالفعل!'),
    ]

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        index=True,
        ondelete='restrict',
        domain=[('is_beneficiary', '=', True)],
        tracking=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
        tracking=True,
    )
    phone = fields.Char(
        related='partner_id.phone',
        string='Phone',
        readonly=False,
    )
    mobile = fields.Char(
        related='partner_id.mobile',
        string='Mobile',
        readonly=False,
    )
    whatsapp_number = fields.Char(
        related='partner_id.whatsapp_number',
        string='WhatsApp Number',
        readonly=False,
    )
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
    )
    extracted_mother_name = fields.Char(
        string='اسم الوالدة',
        tracking=True,
    )
    profession = fields.Char(
        string='Profession',
        size=100,
    )
    marital_status = fields.Selection(
        [
            ('single', 'غير متزوج'),
            ('married', 'متزوج'),
            ('widowed', 'أرمل'),
            ('divorced', 'مطلق'),
        ],
        string='Marital Status',
    )
    gender = fields.Selection(
        [
            ('male', 'ذكر'),
            ('female', 'أنثى'),
        ],
        string='Gender',
        tracking=True,
    )
    family_size = fields.Integer(
        string='Number of Family Members',
        compute='_compute_family_size',
        store=True,
    )
    health_conditions = fields.Many2many(
        'kser.chronic.condition',
        string='الأمراض المزمنة',
    )
    birthdate = fields.Date(
        string='Birth Date',
    )
    def _default_district(self):
        return self.env.company.city or ''

    district = fields.Char(
        string='District',
        size=100,
        required=True,
        index=True,
        default=_default_district,
    )
    registration_date = fields.Date(
        string='Registration Date',
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    is_verified = fields.Boolean(
        string='Is Verified?',
        default=False,
        index=True,
        tracking=True,
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
    )

    is_disabled = fields.Boolean(
        string='Disabled / Special Needs',
        default=False,
        tracking=True,
    )
    is_child = fields.Boolean(
        string='Is Child',
        compute='_compute_is_child',
        store=True,
        tracking=True,
    )
    without_national_id = fields.Boolean(
        string='تسجيل بدون رقم وطني',
    )
    address = fields.Char(
        related='partner_id.street',
        readonly=False,
        string='Address',
    )
    is_head_of_family = fields.Boolean(
        string='هل هو رب أسرة؟ / فرد لوحده',
        default=True,
        tracking=True,
    )
    head_of_family_id = fields.Many2one(
        'kser.beneficiary',
        string='Head of Family',
        index=True,
        ondelete='restrict',
    )
    relationship = fields.Selection(
        [
            ('self', 'رب الأسرة (نفسه)'),
            ('father', 'أب'),
            ('mother', 'أم'),
            ('sibling', 'أخ/أخت'),
            ('grandfather', 'جد'),
            ('grandmother', 'جدة'),
            ('paternal_uncle_aunt', 'عم/عمة'),
            ('maternal_uncle_aunt', 'خال/خالة'),
            ('spouse', 'زوج/زوجة'),
            ('child', 'ابن/ابنة'),
        ],
        string='Relationship to Head of Family',
        default='self',
        required=False,
    )
    member_ids = fields.One2many(
        'kser.beneficiary',
        'head_of_family_id',
        string='Family Members',
        domain=[('relationship', '!=', 'self')],
    )
    family_member_ids = fields.Many2many(
        'kser.beneficiary',
        string='Family Members',
        compute='_compute_family_member_ids',
        inverse='_inverse_family_member_ids',
    )
    family_member_count = fields.Integer(
        compute='_compute_family_member_count',
        string='Family Member Count',
    )
    registered_by = fields.Many2one(
        'res.users',
        string='Registered By',
        default=lambda self: self.env.uid,
    )

    @api.depends('relationship', 'head_of_family_id', 'member_ids', 'member_ids.relationship', 'head_of_family_id.member_ids')
    def _compute_family_size(self):
        for rec in self:
            head = rec if rec.relationship == 'self' else rec.head_of_family_id
            if head:
                if head.id:
                    count = self.env['kser.beneficiary'].search_count([
                        ('head_of_family_id', '=', head.id),
                        ('relationship', '!=', 'self'),
                    ])
                    rec.family_size = 1 + count
                else:
                    rec.family_size = 1 + len(head.member_ids)
            else:
                rec.family_size = 1

    @api.depends('member_ids', 'member_ids.head_of_family_id')
    def _compute_family_member_ids(self):
        for rec in self:
            if rec.relationship == 'self':
                rec.family_member_ids = rec.member_ids
            else:
                rec.family_member_ids = self.env['kser.beneficiary']

    def _inverse_family_member_ids(self):
        for rec in self:
            if rec.relationship != 'self':
                continue
            current_members = rec.family_member_ids
            existing_members = rec.member_ids
            
            added = current_members - existing_members
            for member in added:
                member.write({
                    'head_of_family_id': rec.id,
                    'relationship': rec._determine_auto_relationship(member),
                })
            
            removed = existing_members - current_members
            for member in removed:
                member.write({
                    'head_of_family_id': member.id,
                    'relationship': 'self',
                })

    @api.depends('member_ids')
    def _compute_family_member_count(self):
        for rec in self:
            rec.family_member_count = len(rec.member_ids)

    def action_view_family_members(self):
        self.ensure_one()
        head = self.head_of_family_id or self
        return {
            'name': _('Family Members'),
            'type': 'ir.actions.act_window',
            'res_model': 'kser.beneficiary',
            'view_mode': 'list,form',
            'domain': [('head_of_family_id', '=', head.id), ('relationship', '!=', 'self')],
            'context': {'default_head_of_family_id': head.id},
        }



    @api.constrains('family_size')
    def _check_family_size(self):
        for rec in self:
            if rec.family_size < 1:
                raise ValidationError(_('يجب أن يكون عدد أفراد الأسرة أكبر من صفر!'))


    @api.constrains('head_of_family_id', 'relationship', 'is_head_of_family')
    def _check_family_relationship(self):
        for rec in self:
            if rec.is_head_of_family:
                if rec.relationship != 'self':
                    rec.sudo().write({'relationship': 'self'})
                if not rec.head_of_family_id or rec.head_of_family_id.id != rec.id:
                    rec.sudo().write({'head_of_family_id': rec.id})
            else:
                if not rec.relationship or rec.relationship == 'self':
                    raise ValidationError(_("يجب تحديد صلة قرابة صحيحة لرب الأسرة (لا يمكن أن تكون 'نفسه' للمستفيد التابع)!"))
                if not rec.head_of_family_id or rec.head_of_family_id.id == rec.id:
                    raise ValidationError(_("يجب تحديد رب الأسرة للمستفيد التابع (لا يمكن أن يكون الشخص نفسه)!"))
                if rec.head_of_family_id.is_head_of_family is False:
                    raise ValidationError(_("يجب أن يكون رب الأسرة المسؤول المحدد هو رب أسرة معتمد!"))

    @api.constrains('head_of_family_id', 'relationship', 'extracted_mother_name')
    def _check_relationship_validation(self):
        # التحقق من منطقية علاقة القرابة بناءً على تطابق الأسماء بين المستفيد ورب الأسرة
        # الهدف: منع إدخال علاقات قرابة غير صحيحة بناءً على تشابه الأسماء لتجنب التلاعب
        for rec in self:
            if rec.relationship == 'self' or not rec.head_of_family_id:
                continue
            if not rec.partner_id.name or not rec.head_of_family_id.partner_id.name:
                continue

            head_name = rec.head_of_family_id.partner_id.name.strip().split()
            dep_name = rec.partner_id.name.strip().split()

            # يتطلب التحقق وجود اسمين على الأقل لكل من المستفيد ورب الأسرة
            if len(head_name) < 2 or len(dep_name) < 2:
                continue

            rel = rec.relationship
            if rel in ('spouse', 'maternal_uncle_aunt'):
                continue

            error_msg = _("فشل الحفظ: بيانات الاسم لا تتطابق مع علاقة القرابة المحددة. يرجى تسجيل المستفيد كرب أسرة مستقل.")

            def match_parts(list1, list2):
                min_len = min(len(list1), len(list2))
                if min_len == 0: return False
                return " ".join(list1[:min_len]) == " ".join(list2[:min_len])

            if rel == 'father':
                if not match_parts(dep_name, head_name[1:]):
                    raise ValidationError(error_msg)
            elif rel == 'mother':
                head_mother = rec.head_of_family_id.extracted_mother_name
                name_matched = False
                if head_mother:
                    name_matched = match_parts(dep_name, head_mother.strip().split())
                if not name_matched:
                    if rec.birthdate and rec.head_of_family_id.birthdate:
                        age_diff = relativedelta(rec.head_of_family_id.birthdate, rec.birthdate).years
                        if age_diff < 15:
                            raise ValidationError(_("فشل الحفظ: يجب أن تكون الأم أكبر سنّاً من رب الأسرة بـ 15 عاماً على الأقل."))
                    else:
                        raise ValidationError(error_msg)
            elif rel == 'sibling':
                if not match_parts(dep_name[1:], head_name[1:]):
                    raise ValidationError(error_msg)
            elif rel == 'grandfather':
                if not match_parts(dep_name, head_name[2:]):
                    raise ValidationError(error_msg)
            elif rel == 'grandmother':
                if rec.birthdate and rec.head_of_family_id.birthdate:
                    age_diff = relativedelta(rec.head_of_family_id.birthdate, rec.birthdate).years
                    if age_diff < 30:
                        raise ValidationError(_("فشل الحفظ: فرق السن بين الجدة ورب الأسرة يجب ألا يقل عن 30 عاماً."))
            elif rel == 'paternal_uncle_aunt':
                if not match_parts(dep_name[1:], head_name[2:]):
                    raise ValidationError(error_msg)
            elif rel == 'child':
                if not match_parts(dep_name[1:], head_name):
                    raise ValidationError(error_msg)

    def _determine_auto_relationship(self, dep):
        # استنتاج علاقة القرابة تلقائياً بين المستفيد (dep) ورب الأسرة (self)
        # يعتمد الاستنتاج على مقارنة أجزاء الاسم أو فروق الأعمار في حال عدم تطابق الأسماء
        self.ensure_one()
        head = self
        head_name = head.partner_id.name.strip().split() if head.partner_id.name else []
        dep_name = dep.partner_id.name.strip().split() if dep.partner_id.name else []
        
        def match_parts(list1, list2):
            min_len = min(len(list1), len(list2))
            if min_len == 0: return False
            return " ".join(list1[:min_len]) == " ".join(list2[:min_len])
            
        if dep_name and head_name:
            if match_parts(dep_name[1:], head_name):
                return 'child'
            if match_parts(dep_name, head_name[1:]):
                return 'father'
            if len(dep_name) > 1 and len(head_name) > 1 and match_parts(dep_name[1:], head_name[1:]):
                return 'sibling'
            if head.extracted_mother_name:
                head_mother = head.extracted_mother_name.strip().split()
                if match_parts(dep_name, head_mother):
                    return 'mother'
            if match_parts(dep_name, head_name[2:]):
                return 'grandfather'
            if len(dep_name) > 1 and match_parts(dep_name[1:], head_name[2:]):
                return 'paternal_uncle_aunt'
                
        if dep.birthdate and head.birthdate:
            age_diff = relativedelta(head.birthdate, dep.birthdate).years
            if 18 <= age_diff <= 45:
                return 'mother'
            if age_diff > 45:
                return 'grandfather'
            if -45 <= age_diff <= -18:
                return 'child'
            if -15 <= age_diff <= 15:
                return 'spouse'
                
        return 'spouse'

    @api.onchange('is_head_of_family')
    def _onchange_is_head_of_family(self):
        if self.is_head_of_family:
            self.relationship = 'self'
            self.head_of_family_id = self._origin.id or False
        else:
            if self.relationship == 'self':
                self.relationship = False
            if self.head_of_family_id.id == self.id:
                self.head_of_family_id = False

    @api.onchange('head_of_family_id')
    def _onchange_head_of_family_id(self):
        if self.head_of_family_id and self.head_of_family_id.id != self._origin.id:
            self.is_head_of_family = False
            if self.relationship == 'self':
                self.relationship = 'spouse'
        else:
            self.is_head_of_family = True
            self.relationship = 'self'

    @api.onchange('relationship')
    def _onchange_relationship(self):
        if self.relationship == 'self':
            self.head_of_family_id = self._origin.id or False
            self.is_head_of_family = True
        else:
            self.is_head_of_family = False

    move_ids = fields.One2many(
        'stock.move',
        'beneficiary_id',
        string='Relief Received',
    )
    prescription_ids = fields.One2many(
        'kser.prescription',
        'beneficiary_id',
        string='الروشتات الطبية',
    )
    financial_aid_ids = fields.One2many(
        'kser.cash.expense',
        'beneficiary_id',
        string='المساعدات المالية',
    )
    move_count = fields.Integer(
        compute='_compute_move_count',
        string='Relief Count',
    )

    @api.depends('birthdate')
    def _compute_is_child(self):
        for rec in self:
            if rec.birthdate:
                today = fields.Date.today()
                birthdate = rec.birthdate
                age = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
                rec.is_child = (age < 7)
            else:
                rec.is_child = False

    @api.constrains('national_id_number', 'national_id_image', 'is_child', 'birthdate', 'without_national_id')
    def _check_national_id_beneficiary(self):
        for rec in self:
            if rec.is_child:
                continue
            if rec.without_national_id:
                if rec.national_id_number:
                    if len(rec.national_id_number) != 11 or not rec.national_id_number.isdigit():
                        raise ValidationError(_("يجب أن يتكون الرقم الوطني للمستفيد من 11 خانة رقمية فقط!"))
                continue
            if self.env.user.has_group('kser_erp.group_receptionist'):
                continue
            if not rec.national_id_image:
                raise ValidationError(_("يجب رفع صورة الرقم الوطني للمستفيد!"))
            if not rec.national_id_number or len(rec.national_id_number) != 11 or not rec.national_id_number.isdigit():
                raise ValidationError(_("يجب أن يتكون الرقم الوطني للمستفيد من 11 خانة رقمية فقط!"))

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids.sudo())

    def action_view_moves(self):
        self.ensure_one()
        return {
            'name': _('Relief Received'),
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move',
            'view_mode': 'list,form',
            'domain': [('beneficiary_id', '=', self.id)],
            'context': {'default_beneficiary_id': self.id},
        }

    @api.model
    def name_create(self, name):
        partner = self.env['res.partner'].create({'name': name})
        beneficiary = self.create({'partner_id': partner.id, 'without_national_id': True})
        return beneficiary.id, beneficiary.partner_id.name

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_verified') and not (self.env.user.has_group('kser_erp.group_data_manager') or
                                                 self.env.user.has_group('kser_erp.group_admin_supervisor') or
                                                 self.env.user.has_group('kser_erp.group_system_admin')):
                vals['is_verified'] = False

            # Sync relationship with is_head_of_family
            if 'is_head_of_family' not in vals:
                if vals.get('relationship') == 'self':
                    vals['is_head_of_family'] = True
                elif vals.get('relationship'):
                    vals['is_head_of_family'] = False
                else:
                    vals['is_head_of_family'] = True

            if vals.get('is_head_of_family'):
                vals['relationship'] = 'self'
            else:
                if vals.get('relationship') == 'self':
                    vals['relationship'] = False

        records = super().create(vals_list)
        for rec in records:
            if rec.is_head_of_family:
                if rec.relationship != 'self' or rec.head_of_family_id.id != rec.id:
                    rec.sudo().write({
                        'relationship': 'self',
                        'head_of_family_id': rec.id
                    })
            if rec.partner_id:
                rec.partner_id.sudo().write({
                    'national_id_number': rec.national_id_number,
                    'national_id_image': rec.national_id_image,
                })
        # إضافة وسم (Tag) مخصص للمستفيد لتمييزه في جهات الاتصال
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
        if beneficiary_tag:
            for rec in records:
                if rec.partner_id and rec.partner_id.category_tag != beneficiary_tag:
                    rec.partner_id.sudo().category_tag = beneficiary_tag.id
        # تسجيل عملية الإنشاء في سجل التدقيق (Audit Log) للتتبع الأمني
        for rec in records:
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'create',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم تسجيل مستفيد جديد: الرقم الوطني {rec.national_id_number}، الحي/المنطقة: {rec.district or '-'}",
            })
        return records

    def write(self, vals):
        # Sync relationship and is_head_of_family
        if 'is_head_of_family' in vals:
            if vals['is_head_of_family']:
                vals['relationship'] = 'self'
            else:
                if vals.get('relationship', self.relationship) == 'self':
                    vals['relationship'] = False
        elif 'relationship' in vals:
            if vals['relationship'] == 'self':
                vals['is_head_of_family'] = True
            else:
                vals['is_head_of_family'] = False

        # فصل الحقول التشغيلية (التي لا تحتاج لصلاحيات عالية) عن الحقول الأساسية
        business_fields = set(vals.keys()) - {
            'message_follower_ids', 'activity_ids', 'message_ids',
            'message_main_attachment_id', 'activity_state', 'activity_type_id',
            'activity_date_deadline', 'activity_summary', 'activity_user_id'
        }
        # التحقق من الصلاحيات: منع تعديل البيانات الأساسية إلا لمن يملك الصلاحيات المحددة
        if business_fields and not self.env.su:
            if not (self.env.user.has_group('kser_erp.group_data_manager') or
                    self.env.user.has_group('kser_erp.group_admin_supervisor') or
                    self.env.user.has_group('kser_erp.group_system_admin')):
                raise ValidationError(_("يُمنع تعديل بيانات المستفيد لغير مسؤولي البيانات! يمكنك فقط تسجيل مستفيد جديد."))

        res = super().write(vals)

        # Force sync in database for head of family values
        if 'is_head_of_family' in vals or 'head_of_family_id' in vals or 'relationship' in vals:
            for rec in self:
                if rec.is_head_of_family:
                    if rec.relationship != 'self' or rec.head_of_family_id.id != rec.id:
                        super(KserBeneficiary, rec).write({
                            'relationship': 'self',
                            'head_of_family_id': rec.id
                        })
                else:
                    if rec.relationship == 'self':
                        super(KserBeneficiary, rec).write({
                            'relationship': False
                        })
        if 'national_id_number' in vals or 'national_id_image' in vals:
            for rec in self:
                if rec.partner_id:
                    rec.partner_id.write({
                        'national_id_number': rec.national_id_number,
                        'national_id_image': rec.national_id_image,
                    })
        if 'head_of_family_id' in vals and not vals['head_of_family_id']:
            for rec in self:
                super(KserBeneficiary, rec).write({'head_of_family_id': rec.id})
        if 'partner_id' in vals:
            beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
            if beneficiary_tag:
                for rec in self:
                    if rec.partner_id and rec.partner_id.category_tag != beneficiary_tag:
                        rec.partner_id.category_tag = beneficiary_tag.id
        for rec in self:
            if 'is_verified' in vals and vals['is_verified']:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'approve',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم التحقق من المستفيد (الرقم الوطني: {rec.national_id_number})",
                })
            elif vals and business_fields:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'update',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم تعديل بيانات المستفيد (الرقم الوطني: {rec.national_id_number}). الحقول المعدلة: {list(vals.keys())}",
                })
        return res

    def unlink(self):
        # منع الحذف نهائياً لضمان سلامة قاعدة البيانات وسجلات التدقيق (Data Integrity)
        raise ValidationError(_("يُمنع حذف سجلات المستفيدين بشكل مطلق للحفاظ على سلامة البيانات والتدقيق. إذا لزم الأمر، يمكنك أرشفة السجل أو إيقافه بدلاً من الحذف."))

    def action_open_whatsapp(self):
        self.ensure_one()
        return self.partner_id.action_open_whatsapp()
