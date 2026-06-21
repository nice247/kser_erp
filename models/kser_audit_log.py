from odoo import models, fields, api
from odoo.exceptions import UserError


class KserAuditLog(models.Model):
    _name = 'kser.audit.log'
    _description = 'سجل التدقيق'
    _order = 'timestamp desc'
    _rec_name = 'action_type'

    user_id = fields.Many2one(
        'res.users',
        string='المستخدم',
        required=True,
        index=True,
        default=lambda self: self.env.uid,
    )
    action_type = fields.Selection(
        [
            ('create', 'إنشاء'),
            ('update', 'تعديل'),
            ('delete', 'حذف'),
            ('approve', 'اعتماد'),
        ],
        string='نوع العملية',
        required=True,
    )
    target_model = fields.Char(
        string='الجدول المستهدف',
        size=100,
        required=True,
    )
    target_id = fields.Integer(
        string='معرف السجل المتأثر',
        required=True,
    )
    timestamp = fields.Datetime(
        string='وقت العملية',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    details = fields.Text(
        string='التفاصيل الإضافية',
    )
    ip_address = fields.Char(
        string='عنوان IP',
        size=45,
    )

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS kser_audit_log_target_composite_idx
            ON kser_audit_log (target_model, target_id)
        """)

    def write(self, vals):
        raise UserError('سجل التدقيق للقراءة فقط ولا يمكن تعديله!')

    def unlink(self):
        raise UserError('سجل التدقيق للقراءة فقط ولا يمكن حذفه!')
