from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = "project.project"

    # =========================================================
    # SERVIFLOW / CRM
    # =========================================================

    serviflow_opportunity_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad Serviflow",
        copy=False,
        index=True,
    )

    serviflow_sale_order_ids = fields.Many2many(
        "sale.order",
        "serviflow_project_sale_order_rel",
        "project_id",
        "sale_order_id",
        string="Presupuestos asociados",
        copy=False,
    )

    serviflow_sale_order_count = fields.Integer(
        string="Nº Presupuestos",
        compute="_compute_serviflow_sale_order_count",
    )

    @api.depends("serviflow_sale_order_ids")
    def _compute_serviflow_sale_order_count(self):
        for project in self:
            project.serviflow_sale_order_count = len(
                project.serviflow_sale_order_ids
            )

    # =========================================================
    # ABRIR PRESUPUESTOS DEL PROYECTO
    # =========================================================

    def action_open_serviflow_quotations(self):
        self.ensure_one()

        quotations = self.serviflow_sale_order_ids

        if not quotations:
            raise UserError(
                _("Este proyecto todavía no tiene presupuestos asociados.")
            )

        # Uno solo -> abrir directamente
        if len(quotations) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": quotations.name,
                "res_model": "sale.order",
                "res_id": quotations.id,
                "views": [[False, "form"]],
                "view_mode": "form",
                "target": "current",
            }

        # Varios -> abrir lista
        return {
            "type": "ir.actions.act_window",
            "name": "Presupuestos del proyecto",
            "res_model": "sale.order",
            "view_mode": "tree,form",
            "views": [
                [False, "tree"],
                [False, "form"],
            ],
            "domain": [
                ("id", "in", quotations.ids),
            ],
            "target": "current",
        }

    # =========================================================
    # COMPROBAR FINALIZACIÓN DE TAREAS
    # =========================================================

    def _serviflow_check_tasks_completion(self):
        for project in self:

            # Buscar solicitud principal Serviflow
            serviflow_task = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", project.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            # Proyecto que no pertenece a Serviflow
            if not serviflow_task:
                continue

            # Todas las tareas activas del proyecto
            tasks = self.env["project.task"].sudo().search([
                ("project_id", "=", project.id),
                ("active", "=", True),
            ])

            if not tasks:
                continue

            # Todas deben estar realmente en Hecho
            all_done = all(
                task.state == "1_done"
                for task in tasks
            )

            if not all_done:
                continue

            # Tiene que existir al menos un presupuesto
            if not project.serviflow_sale_order_ids:
                raise UserError(
                    _(
                        "No puedes completar el proyecto porque "
                        "no tiene ningún presupuesto asociado."
                    )
                )

            # Estado Completo del proyecto
            complete_status = self.env["project.status"].sudo().search([
                ("name", "=", "Completo"),
            ], limit=1)

            if not complete_status:
                raise UserError(
                    _("No se encontró el estado de proyecto 'Completo'.")
                )

            # Evitar generar revisiones duplicadas
            if project.project_status == complete_status:
                continue

            # Proyecto -> Completo
            project.sudo().write({
                "project_status": complete_status.id,
            })

            # Solicitud principal Serviflow -> done
            serviflow_task.sudo().write({
                "state": "done",
                "completed_at": fields.Datetime.now(),
            })

            # Crear revisiones
            serviflow_task._create_review_tasks()

            # Chatter
            project.message_post(
                body=(
                    "<b>Proyecto enviado a revisión interna.</b><br/>"
                    "Todas las tareas están completadas y el proyecto "
                    "ha pasado automáticamente a estado Completo."
                )
            )