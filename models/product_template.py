from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    active_ingredient = fields.Char(
        string='Active Ingredient',
    )
    medical_indications = fields.Text(
        string='Medical Indications',
    )
    contraindications = fields.Text(
        string='Contraindications',
    )
    category_path_names = fields.Char(
        string='Category Path Names',
        compute='_compute_category_path_names',
    )
    is_therapeutic = fields.Boolean(
        string='Is Therapeutic',
        compute='_compute_is_therapeutic',
        store=True,
    )

    @api.depends('categ_id', 'categ_id.name', 'categ_id.parent_id')
    def _compute_category_path_names(self):
        for template in self:
            names = []
            category = template.categ_id
            while category:
                if category.name:
                    names.append(category.name.strip())
                category = category.parent_id
            template.category_path_names = " / ".join(names)

    @api.depends('categ_id')
    def _compute_is_therapeutic(self):
        for template in self:
            is_therapeutic = False
            category = template.categ_id
            while category:
                if category.name and 'علاجي' in category.name:
                    is_therapeutic = True
                    break
                category = category.parent_id
            template.is_therapeutic = is_therapeutic
