from odoo import models, fields, api
from collections import Counter

class KserClinicReport(models.AbstractModel):
    _name = 'report.kser_erp.report_clinic_template'
    _description = 'Clinic Performance Report'

    @api.model
    def _get_report_values(self, docids, data=None):
        data = data or {}
        date_from = data.get('date_from', fields.Date.today().replace(month=1, day=1))
        date_to = data.get('date_to', fields.Date.today())

        if isinstance(date_from, str):
            date_from = fields.Date.from_string(date_from)
        if isinstance(date_to, str):
            date_to = fields.Date.from_string(date_to)

        visits = self.env['kser.clinic.visit'].search([
            ('visit_date', '>=', date_from),
            ('visit_date', '<=', date_to),
        ])
        visits_count = len(visits)

        prescriptions = self.env['kser.prescription'].search([
            ('prescription_date', '>=', date_from),
            ('prescription_date', '<=', date_to),
        ])
        prescriptions_count = len(prescriptions)

        child_followups = self.env['kser.child.followup'].search([
            ('followup_date', '>=', date_from),
            ('followup_date', '<=', date_to),
        ])

        visiting_beneficiaries = visits.mapped('beneficiary_id')

        new_patients_count = 0
        for ben in visiting_beneficiaries:
            earliest_visit = self.env['kser.clinic.visit'].search([
                ('beneficiary_id', '=', ben.id),
            ], order='visit_date asc, visit_time asc', limit=1)
            if earliest_visit and earliest_visit.visit_date >= date_from:
                new_patients_count += 1

        visits_count_returning = max(0, visits_count - new_patients_count)

        dispensed_prescriptions = prescriptions.filtered(lambda r: r.state == 'dispensed')
        dispensed_medicines_count = sum(sum(line.qty for line in p.line_ids) for p in dispensed_prescriptions)

        medicine_counter = Counter()
        for p in dispensed_prescriptions:
            for line in p.line_ids:
                medicine_counter[line.product_id.name] += line.qty

        top_medicines = []
        for name, qty in medicine_counter.most_common(5):
            top_medicines.append({
                'name': name,
                'qty': qty
            })

        malnourished_children_count = len(child_followups.mapped('beneficiary_id'))

        weight_diffs = []
        for child in child_followups.mapped('beneficiary_id'):
            child_records = child_followups.filtered(lambda r: r.beneficiary_id.id == child.id).sorted('followup_date')
            if len(child_records) > 1:
                diff = child_records[-1].weight - child_records[0].weight
                weight_diffs.append(diff)

        avg_weight_evolution = sum(weight_diffs) / len(weight_diffs) if weight_diffs else 0.0

        return {
            'doc_ids': docids,
            'doc_model': 'kser.prescription',
            'company': self.env.company,
            'date_from': date_from,
            'date_to': date_to,
            'new_patients_count': new_patients_count,
            'visits_count': visits_count_returning,
            'prescriptions_count': prescriptions_count,
            'dispensed_medicines_count': dispensed_medicines_count,
            'top_medicines': top_medicines,
            'malnourished_children_count': malnourished_children_count,
            'avg_weight_evolution': avg_weight_evolution,
        }
