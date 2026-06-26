from odoo.addons.web.controllers.webmanifest import WebManifest
from odoo.tools import file_open


class KserWebManifest(WebManifest):

    def _get_service_worker_content(self):
        body = super()._get_service_worker_content()

        with file_open('kser_erp/static/src/js/kser_service_worker.js') as f:
            kser_sw_code = f.read()

        body += "\n\n" + kser_sw_code
        return body
