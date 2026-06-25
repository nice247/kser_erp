import base64
import logging

from odoo import models, fields
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class KserDonorImportWizard(models.TransientModel):
    _name = 'kser.donor.import.wizard'
    _description = 'معالج استيراد كشوفات المانحين'

    file = fields.Binary(
        string='ملف Excel',
        required=True,
    )
    file_name = fields.Char(
        string='اسم الملف',
    )
    project_id = fields.Many2one(
        'project.project',
        string='الحملة',
        required=True,
    )

    def process_import_data(self, parsed_data=None):
        self.ensure_one()

        if parsed_data is None:
            parsed_data = self._parse_excel_file()

        base_currency = self.env.company.currency_id
        company = self.env.company
        today = fields.Date.today()

        journal = self.env['account.journal'].search([
            ('type', '=', 'bank'),
            ('company_id', '=', company.id),
        ], limit=1)

        if not journal:
            raise UserError('لا يوجد دفتر يومية بنكي مُعرّف في النظام!')

        created_payments = self.env['account.payment']

        for row in parsed_data:
            foreign_currency = self.env['res.currency'].search([
                ('name', '=', row['currency_code']),
                ('active', 'in', [True, False]),
            ], limit=1)

            if not foreign_currency:
                raise UserError(
                    'العملة "%s" غير موجودة في النظام!' % row['currency_code']
                )

            if foreign_currency == base_currency:
                converted_amount = row['amount']
            else:
                converted_amount = foreign_currency._convert(
                    row['amount'],
                    base_currency,
                    company,
                    today,
                )

            donor = self.env['res.partner'].search([
                ('name', '=', row['donor_name']),
            ], limit=1)

            if not donor:
                donor = self.env['res.partner'].create({
                    'name': row['donor_name'],
                })

            payment = self.env['account.payment'].create({
                'payment_type': 'inbound',
                'partner_type': 'customer',
                'partner_id': donor.id,
                'amount': converted_amount,
                'currency_id': base_currency.id,
                'journal_id': journal.id,
                'ref': row.get('receipt_no', ''),
                'date': today,
            })

            self.env['kser.cash.donation'].create({
                'campaign_id': self.project_id.id,
                'amount': converted_amount,
                'currency_id': base_currency.id,
                'transaction_number': row.get('receipt_no', ''),
                'bank_name': row.get('bank_name', '-'),
                'sender_account_number': row.get('sender_account', '-'),
                'receiver_account_number': row.get('receiver_account', '-'),
                'donation_date': today,
                'move_id': payment.move_id.id if payment.move_id else False,
                'created_by': self.env.uid,
            })

            created_payments |= payment

        return created_payments

    def _parse_excel_file(self):
        if not self.file:
            raise UserError('يرجى رفع ملف Excel أولاً!')

        try:
            import openpyxl
            from io import BytesIO
        except ImportError:
            raise UserError('مكتبة openpyxl غير مثبتة!')

        file_content = base64.b64decode(self.file)
        workbook = openpyxl.load_workbook(BytesIO(file_content), read_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(min_row=2, values_only=True))

        parsed = []
        for row in rows:
            if not row[0]:
                continue
            parsed.append({
                'donor_name': str(row[0]).strip(),
                'amount': float(row[1]),
                'currency_code': str(row[2]).strip().upper(),
                'receipt_no': str(row[3]).strip() if row[3] else '',
            })

        workbook.close()
        return parsed
