/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

export class OcrListController extends ListController {
    static template = "kser_erp.ListView";

    setup() {
        super.setup();
    }
    
    async onClickOcr() {
        // Find which action to call based on the model
        let action_xmlid = '';
        if (this.props.resModel === 'res.partner') {
            action_xmlid = 'kser_erp.action_kser_national_id_wizard_volunteer';
        } else if (this.props.resModel === 'kser.beneficiary') {
            action_xmlid = 'kser_erp.action_kser_national_id_wizard';
        } else if (this.props.resModel === 'kser.cash.donation') {
            action_xmlid = 'kser_erp.action_kser_bank_receipt_wizard';
        }
        
        if (action_xmlid) {
            this.env.services.action.doAction(action_xmlid);
        }
    }
}

export const ocrListView = {
    ...listView,
    Controller: OcrListController,
};

registry.category("views").add("kser_ocr_list", ocrListView);
