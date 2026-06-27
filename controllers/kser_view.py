# -*- coding: utf-8 -*-
from odoo import http
from odoo.addons.web.controllers.view import View
from odoo.http import request


class KSERView(View):

    @http.route('/web/view/edit_custom', type='json', auth="user")
    def edit_custom(self, custom_id=None, arch=None, **kwargs):
        """
        Override edit_custom to handle missing/falsy custom_id gracefully.
        This prevents RPC errors when users interact with fresh dashboards
        that haven't been saved to custom views yet.
        """
        if not custom_id:
            return {'result': True}
        return super().edit_custom(custom_id, arch, **kwargs)
