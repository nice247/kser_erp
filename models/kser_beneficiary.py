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
        ('partner_id_unique', 'UNIQUE(partner_id)', 'This contact is already linked to another beneficiary!'),
        ('national_id_unique', 'UNIQUE(national_id_number)', 'This National ID is already registered!'),
    ]

    partner_id = fields.Many2one(
        'res.partner',
        string='Contact',
        required=True,
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    national_id_number = fields.Char(
        string='National ID Number',
        size=20,
        required=True,
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
    national_id_image = fields.Binary(
        string='ID Image',
        attachment=True,
        required=True,
    )
    profession = fields.Char(
        string='Profession',
        size=100,
    )
    marital_status = fields.Selection(
        [
            ('single', 'Single'),
            ('married', 'Married'),
            ('widowed', 'Widowed'),
            ('divorced', 'Divorced'),
        ],
        string='Marital Status',
    )
    family_size = fields.Integer(
        string='Number of Family Members',
        compute='_compute_family_size',
        store=True,
    )
    health_conditions = fields.Text(
        string='Chronic Diseases',
    )
    birthdate = fields.Date(
        string='Birth Date',
    )
    district = fields.Char(
        string='District',
        size=100,
        required=True,
        index=True,
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
    ocr_confidence = fields.Float(
        string='OCR Confidence',
        readonly=True,
    )
    priority_score = fields.Integer(
        string='Priority Score',
        compute='_compute_priority',
        store=True,
    )
    priority_level = fields.Selection(
        [
            ('normal', 'Normal'),
            ('medium', 'Medium'),
            ('urgent', 'Urgent'),
        ],
        string='Priority Level',
        compute='_compute_priority',
        store=True,
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
            ('spouse', 'زوج/زوجة'),
            ('child', 'ابن/ابنة'),
            ('parent', 'أب/أم'),
            ('sibling', 'أخ/أخت'),
            ('relative', 'قريب آخر'),
        ],
        string='Relationship to Head of Family',
        default='self',
        required=True,
    )
    member_ids = fields.One2many(
        'kser.beneficiary',
        'head_of_family_id',
        string='Family Members',
        domain=[('relationship', '!=', 'self')],
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

    @api.depends(
        'relationship',
        'head_of_family_id',
        'member_ids',
        'member_ids.relationship',
        'health_conditions',
        'marital_status',
        'family_size',
        'birthdate',
        'member_ids.health_conditions',
        'member_ids.marital_status',
        'member_ids.birthdate',
    )
    def _compute_priority(self):
        today = fields.Date.today()
        for rec in self:
            if rec.relationship != 'self':
                rec.priority_score = 0
                rec.priority_level = 'normal'
                continue
            score = 0
            all_members = [rec]
            if rec.id:
                dependants = self.env['kser.beneficiary'].search([
                    ('head_of_family_id', '=', rec.id),
                    ('relationship', '!=', 'self'),
                ])
                all_members.extend(dependants)
            else:
                all_members.extend(rec.member_ids)
            for member in all_members:
                if member.health_conditions:
                    score += 30
                if member.marital_status in ('widowed', 'divorced'):
                    score += 20
                if member.birthdate:
                    age = relativedelta(today, member.birthdate).years
                    if age >= 60:
                        score += 15
            if rec.family_size > 3:
                score += (rec.family_size - 3) * 5
            rec.priority_score = min(score, 100)
            if rec.priority_score >= 80:
                rec.priority_level = 'urgent'
            elif rec.priority_score >= 50:
                rec.priority_level = 'medium'
            else:
                rec.priority_level = 'normal'

    @api.constrains('family_size')
    def _check_family_size(self):
        for rec in self:
            if rec.family_size < 1:
                raise ValidationError(_('Family size must be greater than zero!'))

    @api.constrains('ocr_confidence')
    def _check_ocr_confidence(self):
        for rec in self:
            if rec.ocr_confidence and not (0 <= rec.ocr_confidence <= 1):
                raise ValidationError(_('OCR confidence must be between 0 and 1!'))

    def _preprocess_image(self, image_base64):
        if not image_base64:
            return False
        try:
            import io
            from PIL import Image, ImageOps
            import base64
            image_bytes = base64.b64decode(image_base64)
            img = Image.open(io.BytesIO(image_bytes))
            img = ImageOps.exif_transpose(img)
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                img = img.convert('RGB')
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=95)
            return base64.b64encode(output.getvalue()).decode('utf-8')
        except Exception:
            return image_base64

    @api.onchange('national_id_image')
    def _onchange_national_id_image(self):
        if not self.national_id_image:
            return
        cleaned_image = self._preprocess_image(self.national_id_image)
        if cleaned_image:
            self.national_id_image = cleaned_image
        api_key = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_api_key')
        base_url = self.env['ir.config_parameter'].sudo().get_param('kser.springboot_base_url')
        if not api_key or not base_url:
            return {
                'warning': {
                    'title': _('Configuration Error'),
                    'message': _('Spring Boot API credentials are not configured!')
                }
            }
        base_url = base_url.rstrip('/')
        import base64
        image_bytes = base64.b64decode(self.national_id_image)
        try:
            import requests
            response = requests.post(
                f'{base_url}/api/v1/ocr/national-id',
                files={'image': ('national_id.jpg', image_bytes, 'image/jpeg')},
                headers={'X-API-KEY': api_key},
                timeout=30,
            )
            result = response.json()
        except Exception as e:
            return {
                'warning': {
                    'title': _('OCR Connection Error'),
                    'message': _('Connection failed: %s') % str(e)
                }
            }
        if not result.get('success'):
            backend_msg = result.get('message', '')
            errors = result.get('data', {}).get('errors', [])
            detailed_errors = ', '.join(errors) if errors else ''
            error_msg = f"{backend_msg} (Details: {detailed_errors})" if detailed_errors else backend_msg
            return {
                'warning': {
                    'title': _('OCR Extraction Failed'),
                    'message': error_msg
                }
            }
        data = result.get('data', {})
        extracted_dob = data.get('dateOfBirth', '')
        birthdate = False
        if extracted_dob:
            from datetime import datetime
            for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y'):
                try:
                    birthdate = datetime.strptime(extracted_dob, fmt).date()
                    break
                except ValueError:
                    continue
        extracted_id = data.get('nationalIdNumber', '')
        if extracted_id:
            existing = self.env['kser.beneficiary'].search([
                ('national_id_number', '=', extracted_id),
            ], limit=1)
            if existing:
                return {
                    'warning': {
                        'title': _('Duplicate National ID'),
                        'message': _('A beneficiary with National ID "%s" is already registered!') % extracted_id
                    }
                }
        MARITAL_STATUS_MAP = {
            'أعزب': 'single',
            'متزوج': 'married',
            'متزوجة': 'married',
            'أرمل': 'widowed',
            'أرملة': 'widowed',
            'أرمل/ة': 'widowed',
            'مطلق': 'divorced',
            'مطلقة': 'divorced',
            'مطلق/ة': 'divorced',
        }
        marital_key = MARITAL_STATUS_MAP.get(data.get('maritalStatus', ''), False)
        self.national_id_number = extracted_id
        self.profession = data.get('profession', '')
        self.marital_status = marital_key
        self.birthdate = birthdate
        self.ocr_confidence = data.get('ocr_confidence', 0.0)
        extracted_name = data.get('name', '')
        if extracted_name:
            beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
            new_partner = self.env['res.partner'].create({
                'name': extracted_name,
                'category_tag': beneficiary_tag.id if beneficiary_tag else False,
            })
            self.partner_id = new_partner.id

    @api.constrains('head_of_family_id', 'relationship')
    def _check_family_relationship(self):
        for rec in self:
            if rec.head_of_family_id and rec.head_of_family_id.id != rec._origin.id:
                if rec.relationship == 'self':
                    raise ValidationError(_("لا يمكن اختيار 'رب الأسرة (نفسه)' إذا كان هناك رب أسرة آخر محدد!"))
            else:
                if rec.relationship != 'self':
                    raise ValidationError(_("يجب أن تكون العلاقة 'رب الأسرة (نفسه)' إذا كان الشخص هو رب الأسرة!"))

    @api.onchange('head_of_family_id')
    def _onchange_head_of_family_id(self):
        if self.head_of_family_id and self.head_of_family_id.id != self._origin.id:
            if self.relationship == 'self':
                self.relationship = 'spouse'
        else:
            self.relationship = 'self'

    @api.onchange('relationship')
    def _onchange_relationship(self):
        if self.relationship == 'self':
            self.head_of_family_id = self._origin.id or False

    move_ids = fields.One2many(
        'stock.move',
        'beneficiary_id',
        string='Relief Received',
    )
    move_count = fields.Integer(
        compute='_compute_move_count',
        string='Relief Count',
    )

    @api.constrains('national_id_number', 'national_id_image')
    def _check_national_id_beneficiary(self):
        for rec in self:
            if not rec.national_id_image:
                raise ValidationError(_("يجب رفع صورة الرقم الوطني للمستفيد!"))
            if not rec.national_id_number or len(rec.national_id_number) != 11 or not rec.national_id_number.isdigit():
                raise ValidationError(_("يجب أن يتكون الرقم الوطني للمستفيد من 11 خانة رقمية فقط!"))

    @api.depends('move_ids')
    def _compute_move_count(self):
        for rec in self:
            rec.move_count = len(rec.move_ids)

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

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.head_of_family_id:
                rec.head_of_family_id = rec.id
        beneficiary_tag = self.env.ref('kser_erp.partner_category_beneficiary', raise_if_not_found=False)
        if beneficiary_tag:
            for rec in records:
                if rec.partner_id and rec.partner_id.category_tag != beneficiary_tag:
                    rec.partner_id.category_tag = beneficiary_tag.id
        for rec in records:
            self.env['kser.audit.log'].sudo().create({
                'action_type': 'create',
                'target_model': self._name,
                'target_id': rec.id,
                'details': f"تم تسجيل مستفيد جديد: الرقم الوطني {rec.national_id_number}، الحي/المنطقة: {rec.district or '-'}",
            })
        return records

    def write(self, vals):
        res = super().write(vals)
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
            elif vals:
                self.env['kser.audit.log'].sudo().create({
                    'action_type': 'update',
                    'target_model': self._name,
                    'target_id': rec.id,
                    'details': f"تم تعديل بيانات المستفيد (الرقم الوطني: {rec.national_id_number}). الحقول المعدلة: {list(vals.keys())}",
                })
        return res
