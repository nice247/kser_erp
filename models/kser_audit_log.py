from odoo import models, fields, api
from odoo.exceptions import UserError
from odoo.tools.translate import _


class KserAuditLog(models.Model):
    _name = 'kser.audit.log'
    _description = 'Audit Log'
    _order = 'timestamp desc'
    _rec_name = 'action_type'

    user_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        index=True,
        default=lambda self: self.env.uid,
    )
    action_type = fields.Selection(
        [
            ('create', 'Create'),
            ('update', 'Update'),
            ('delete', 'Delete'),
            ('approve', 'Approve'),
        ],
        string='Action Type',
        required=True,
    )
    target_model = fields.Char(
        string='Target Model',
        size=100,
        required=True,
    )
    target_id = fields.Integer(
        string='Affected Record ID',
        required=True,
    )
    timestamp = fields.Datetime(
        string='Timestamp',
        required=True,
        default=fields.Datetime.now,
        index=True,
    )
    details = fields.Text(
        string='Additional Details',
    )
    ip_address = fields.Char(
        string='IP Address',
        size=45,
    )

    def init(self):
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS kser_audit_log_target_composite_idx
            ON kser_audit_log (target_model, target_id)
        """)

    def write(self, vals):
        raise UserError(_('سجل التدقيق للقراءة فقط ولا يمكن تعديله!'))

    def unlink(self):
        raise UserError(_('سجل التدقيق للقراءة فقط ولا يمكن حذفه!'))
