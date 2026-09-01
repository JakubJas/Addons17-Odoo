/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { ActivityMenu } from "@mail/core/web/activity_menu";
import { useService } from "@web/core/utils/hooks";
import { useState } from "@odoo/owl";

patch(ActivityMenu.prototype, {
    setup() {
        super.setup();

        this.orm = useService("orm");
        this.notification = useService("notification");

        this.serviflow = useState({
            tasks: [],
            reviews: [],
        });
    },

    async onBeforeOpen() {
        await super.onBeforeOpen();

        await this.loadServiflowTasks();
        await this.loadServiflowReviews();
    },

    async loadServiflowReviews() {
        this.serviflow.reviews = await this.orm.call(
            "serviflow.task",
            "get_my_pending_systray_reviews",
            [],
            {}
        );
    },

    async loadServiflowTasks() {
        this.serviflow.tasks = await this.orm.call(
            "serviflow.task",
            "get_my_pending_systray_tasks",
            [],
            {}
        );
    },

    async approveServiflowReview(taskId) {
        try {
            await this.orm.call(
                "serviflow.task",
                "action_review_approve",
                [[taskId]],
                {}
            );

            this.notification.add(
                "Revisión aprobada correctamente.",
                {
                    type: "success",
                }
            );

            await this.loadServiflowReviews();
            await this.fetchSystrayActivities();

        } catch (error) {
            this.notification.add(
                "No se ha podido aprobar la revisión.",
                {
                    type: "warning",
                }
            );
        }
    },

    async acceptServiflowTask(taskId) {
        try {
            await this.orm.call(
                "serviflow.task",
                "action_accept",
                [[taskId]],
                {}
            );

            this.notification.add(
                "Solicitud aceptada correctamente.",
                {
                    type: "success",
                }
            );

            await this.loadServiflowTasks();
            await this.fetchSystrayActivities();

        } catch (error) {
            this.notification.add(
                "La solicitud ya no está disponible o no ha podido aceptarse.",
                {
                    type: "warning",
                }
            );
        }
    },
});