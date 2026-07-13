from odoo import models, fields, api, _
from odoo.exceptions import UserError

class KserChildFollowup(models.Model):
    _name = 'kser.child.followup'
    _description = 'Child Malnutrition Follow-up'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'beneficiary_id'
    _sql_constraints = [
        ('beneficiary_unique', 'UNIQUE(beneficiary_id)', 'هذا الطفل لديه سجل متابعة بالفعل! يمكنك تعديل سجله الحالي وإضافة قياسات جديدة للزيارة.'),
    ]

    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='Child Beneficiary',
        required=True,
        domain="[('is_child', '=', True)]",
        tracking=True,
    )
    child_age = fields.Char(
        string='عمر الطفل',
        compute='_compute_child_age',
        readonly=True,
    )
    line_ids = fields.One2many(
        'kser.child.followup.line',
        'followup_id',
        string='زيارات المتابعة والقياسات',
    )
    prescription_ids = fields.One2many(
        'kser.prescription',
        'followup_id',
        string='الروشتات الطبية',
    )

    # Computed fields storing the latest visit values
    followup_date = fields.Date(
        string='تاريخ آخر فحص',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    weight = fields.Float(
        string='الوزن الأخير (كجم)',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    height = fields.Float(
        string='الطول الأخير (سم)',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    nutrition_status = fields.Selection([
        ('severe', 'Severe Malnutrition'),
        ('moderate', 'Moderate Malnutrition'),
        ('normal', 'Normal / Recovered'),
    ], string='الحالة الغذائية الأخيرة',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    next_visit_date = fields.Date(
        string='موعد الزيارة القادمة',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    visit_location = fields.Selection([
        ('home', 'زيارة منزلية'),
        ('clinic', 'حضور للعيادة'),
    ], string='مكان الزيارة الأخيرة',
        compute='_compute_latest_values',
        store=True,
        tracking=True,
    )
    state = fields.Selection([
        ('active', 'تحت المتابعة'),
        ('recovered', 'سليم ومتعافي'),
    ], string='حالة المتابعة', default='active', compute='_compute_state', store=True, readonly=False, tracking=True)

    @api.depends('nutrition_status')
    def _compute_state(self):
        for rec in self:
            if rec.nutrition_status == 'normal':
                rec.state = 'recovered'
            else:
                rec.state = 'active'

    @api.depends('beneficiary_id')
    def _compute_child_age(self):
        for rec in self:
            if rec.beneficiary_id and rec.beneficiary_id.birthdate:
                birthdate = rec.beneficiary_id.birthdate
                today = fields.Date.context_today(self)
                years = today.year - birthdate.year - ((today.month, today.day) < (birthdate.month, birthdate.day))
                months = (today.month - birthdate.month) % 12
                if today.day < birthdate.day:
                    months -= 1
                    if months < 0:
                        months = 11
                if years > 0:
                    rec.child_age = f"{years} سنة و {months} شهر"
                else:
                    rec.child_age = f"{months} شهر"
            else:
                rec.child_age = "غير معروف"

    @api.depends('line_ids', 'line_ids.followup_date', 'line_ids.weight', 'line_ids.height', 'line_ids.nutrition_status', 'line_ids.next_visit_date', 'line_ids.visit_location')
    def _compute_latest_values(self):
        for rec in self:
            if rec.line_ids:
                # Sort lines by date desc, then id desc to get the latest check-up
                sorted_lines = rec.line_ids.sorted(key=lambda l: (l.followup_date or fields.Date.today(), l.id or 0), reverse=True)
                latest = sorted_lines[0]
                rec.followup_date = latest.followup_date
                rec.weight = latest.weight
                rec.height = latest.height
                rec.nutrition_status = latest.nutrition_status
                rec.next_visit_date = latest.next_visit_date
                rec.visit_location = latest.visit_location
            else:
                rec.followup_date = False
                rec.weight = 0.0
                rec.height = 0.0
                rec.nutrition_status = False
                rec.next_visit_date = False
                rec.visit_location = False


class KserChildFollowupLine(models.Model):
    _name = 'kser.child.followup.line'
    _description = 'Child Malnutrition Follow-up Visit'
    _order = 'followup_date desc, id desc'

    followup_id = fields.Many2one(
        'kser.child.followup',
        string='Follow-up Record',
        required=True,
        ondelete='cascade',
    )
    beneficiary_id = fields.Many2one(
        'kser.beneficiary',
        string='الطفل المستفيد',
        related='followup_id.beneficiary_id',
        store=True,
        readonly=True,
    )
    followup_date = fields.Date(
        string='تاريخ الفحص',
        required=True,
        default=fields.Date.context_today,
    )
    weight = fields.Float(
        string='الوزن (كجم)',
        required=True,
    )
    weight_difference = fields.Float(
        string='تغير الوزن (كجم)',
        compute='_compute_measurements_difference',
        readonly=True,
    )
    height = fields.Float(
        string='الطول (سم)',
        required=True,
    )
    height_difference = fields.Float(
        string='تغير الطول (سم)',
        compute='_compute_measurements_difference',
        readonly=True,
    )
    nutrition_status = fields.Selection([
        ('severe', 'Severe Malnutrition'),
        ('moderate', 'Moderate Malnutrition'),
        ('normal', 'Normal / Recovered'),
    ], string='الحالة الغذائية', required=True)

    notes = fields.Text(
        string='ملاحظات الفحص',
    )
    measured_by = fields.Many2one(
        'res.users',
        string='تم القياس بواسطة',
        required=True,
        default=lambda self: self.env.user,
    )
    visit_id = fields.Many2one(
        'kser.clinic.visit',
        string='زيارة العيادة',
    )
    next_visit_date = fields.Date(
        string='موعد الزيارة القادمة',
    )
    visit_location = fields.Selection([
        ('home', 'زيارة منزلية'),
        ('clinic', 'حضور للعيادة'),
    ], string='مكان الزيارة', default='clinic')

    @api.model_create_multi
    def create(self, vals_list):
        lines = super(KserChildFollowupLine, self).create(vals_list)
        for line in lines:
            # Find the previous check-up line for this child (excluding this one)
            previous = self.search([
                ('followup_id', '=', line.followup_id.id),
                ('id', '!=', line.id)
            ], order='followup_date desc, id desc', limit=1)
            
            if previous:
                msg_parts = []
                w_diff = line.weight - previous.weight
                if w_diff > 0:
                    msg_parts.append(f"• <b>الوزن:</b> زاد بمقدار <span style='color:green;'>+{w_diff:.2f} كجم</span> (تحسن)")
                elif w_diff < 0:
                    msg_parts.append(f"• <b>الوزن:</b> نقص بمقدار <span style='color:red;'>{w_diff:.2f} كجم</span> (تراجع)")
                else:
                    msg_parts.append("• <b>الوزن:</b> ثابت")

                h_diff = line.height - previous.height
                if h_diff > 0:
                    msg_parts.append(f"• <b>الطول:</b> زاد بمقدار <span style='color:green;'>+{h_diff:.2f} سم</span> (نمو)")
                elif h_diff < 0:
                    msg_parts.append(f"• <b>الطول:</b> نقص بمقدار <span style='color:red;'>{h_diff:.2f} سم</span>")
                else:
                    msg_parts.append("• <b>الطول:</b> ثابت")

                status_labels = {
                    'severe': 'سوء تغذية حاد',
                    'moderate': 'سوء تغذية متوسط',
                    'normal': 'طبيعي / متعافي'
                }
                status_scores = {
                    'severe': 1,
                    'moderate': 2,
                    'normal': 3
                }
                prev_score = status_scores.get(previous.nutrition_status, 0)
                curr_score = status_scores.get(line.nutrition_status, 0)
                prev_label = status_labels.get(previous.nutrition_status, previous.nutrition_status)
                curr_label = status_labels.get(line.nutrition_status, line.nutrition_status)

                if curr_score > prev_score:
                    msg_parts.append(f"• <b>الحالة الغذائية:</b> تحسنت من (<b>{prev_label}</b>) إلى (<b style='color:green;'>{curr_label}</b>)")
                elif curr_score < prev_score:
                    msg_parts.append(f"• <b>الحالة الغذائية:</b> تراجعت من (<b>{prev_label}</b>) إلى (<b style='color:red;'>{curr_label}</b>)")
                else:
                    msg_parts.append(f"• <b>الحالة الغذائية:</b> ثابتة على (<b>{curr_label}</b>)")

                chatter_msg = f"<b>تقرير مقارنة التقييم للزيارة الجديدة (بتاريخ {line.followup_date}) مقارنة بالزيارة السابقة ({previous.followup_date}):</b><br/>" + "<br/>".join(msg_parts)
                line.followup_id.message_post(body=chatter_msg)
        return lines

    def unlink(self):
        raise UserError(_("لا يُسمح بحذف زيارات المتابعة الطبية للأطفال حفاظاً على الأرشيف الطبي."))

    @api.depends('weight', 'height', 'followup_date')
    def _compute_measurements_difference(self):
        for rec in self:
            domain = [
                ('followup_id', '=', rec.followup_id.id),
            ]
            if rec.id:
                domain.append(('id', '!=', rec.id))
            
            all_lines = self.search(domain, order='followup_date asc, id asc')
            
            previous = False
            for line in reversed(all_lines):
                if (line.followup_date < rec.followup_date) or (line.followup_date == rec.followup_date and (not rec.id or line.id < rec.id)):
                    previous = line
                    break
            
            if previous:
                rec.weight_difference = rec.weight - previous.weight
                rec.height_difference = rec.height - previous.height
            else:
                rec.weight_difference = 0.0
                rec.height_difference = 0.0
