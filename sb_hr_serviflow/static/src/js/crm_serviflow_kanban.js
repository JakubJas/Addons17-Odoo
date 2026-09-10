/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { CrmKanbanRenderer } from "@crm/views/crm_kanban/crm_kanban_renderer";

patch(CrmKanbanRenderer.prototype, {

    setup() {
        super.setup();

        this.orm = useService("orm");
        this.actionService = useService("action");
    },

    async sortRecordDrop(dataRecordId, dataGroupId, params) {

        const { element, parent } = params;

        // Si por algún motivo no tenemos columna destino,
        // dejamos trabajar al comportamiento estándar.
        if (!parent) {
            return await super.sortRecordDrop(...arguments);
        }

        // El ID del grupo destino está realmente aquí en Odoo 17.
        const targetGroupId = parent.dataset.id;

        if (!targetGroupId) {
            return await super.sortRecordDrop(...arguments);
        }

        const serviflowStageId = await this.orm.call(
            "crm.lead",
            "get_serviflow_budget_stage_id",
            [],
            {}
        );

        if (!serviflowStageId) {
            return await super.sortRecordDrop(...arguments);
        }

        /*
         * IMPORTANTE:
         * dataGroupId y targetGroupId NO son necesariamente
         * el stage_id de CRM.
         *
         * Son IDs internos de los grupos del kanban.
         *
         * Tenemos que localizar el grupo destino y obtener
         * su valor real (stage_id).
         */

        const targetGroup = this.props.list.groups.find(
            (group) => String(group.id) === String(targetGroupId)
        );

        if (!targetGroup) {
            return await super.sortRecordDrop(...arguments);
        }

        let targetStageId = targetGroup.value;

        /*
         * En muchos grupos many2one, value puede venir:
         *
         * [3, "Solicitado Presupuesto Técnico"]
         *
         * o directamente como ID.
         */
        if (Array.isArray(targetStageId)) {
            targetStageId = targetStageId[0];
        }

        targetStageId = parseInt(targetStageId);

        // Si NO es la etapa Serviflow, comportamiento normal.
        if (targetStageId !== parseInt(serviflowStageId)) {
            return await super.sortRecordDrop(...arguments);
        }

        // -----------------------------------------------------
        // ES SOLICITADO PRESUPUESTO TÉCNICO
        // -----------------------------------------------------

        // Recuperar el registro real.
        let record = null;

        for (const group of this.props.list.groups) {
            const found = group.list.records.find(
                (r) => String(r.id) === String(dataRecordId)
            );

            if (found) {
                record = found;
                break;
            }
        }

        if (!record || !record.resId) {
            console.error(
                "Serviflow: no se pudo localizar el lead",
                dataRecordId
            );

            return await super.sortRecordDrop(...arguments);
        }

        // Como NO llamamos al super, la tarjeta todavía
        // no cambia realmente de etapa.

        await this.actionService.doAction({
            type: "ir.actions.act_window",
            name: "Solicitar Presupuesto Técnico",
            res_model: "serviflow.request.budget.wizard",

            views: [
                [false, "form"],
            ],

            target: "new",

            context: {
                default_opportunity_id: record.resId,
            },
        });

        /*
         * NO llamar a:
         *
         * super.sortRecordDrop(...)
         *
         * El wizard será quien cambie stage_id después
         * de pulsar "Enviar a Oficina Técnica".
         */
        return;
    },

});