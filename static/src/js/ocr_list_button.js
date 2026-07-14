/** @odoo-module **/

import { registry } from "@web/core/registry";
import { listView } from "@web/views/list/list_view";
import { ListController } from "@web/views/list/list_controller";

import { useService } from "@web/core/utils/hooks";

export class OcrListController extends ListController {
    static template = "kser_erp.ListView";

    setup() {
        super.setup();
        this.orm = useService("orm");
        this.actionService = useService("action");
    }

    async openRecord(record, force = false) {
        if (this.props.resModel === 'res.partner' && record.data.is_beneficiary) {
            try {
                const beneficiaryIds = await this.orm.search("kser.beneficiary", [["partner_id", "=", record.resId]], { limit: 1 });
                if (beneficiaryIds.length > 0) {
                    this.actionService.doAction({
                        type: "ir.actions.act_window",
                        res_model: "kser.beneficiary",
                        res_id: beneficiaryIds[0],
                        views: [[false, "form"]],
                        target: "current",
                        context: this.props.context,
                    });
                    return;
                }
            } catch (err) {
                console.error("Error redirecting to beneficiary form:", err);
            }
        }
        super.openRecord(record, force);
    }
    
    async onClickOcr() {
        // تحديد الأكشن المطلوب استدعاؤه بناءً على الموديل (Model)
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
