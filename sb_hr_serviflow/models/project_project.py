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

            # -----------------------------------------------------
            # Solo proyectos vinculados a Serviflow
            # -----------------------------------------------------

            serviflow_task = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", project.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            if not serviflow_task:
                continue

            # -----------------------------------------------------
            # El proyecto debe estar en estado COMPLETO
            # -----------------------------------------------------

            complete_status = self.env["project.status"].sudo().search([
                ("name", "=", "Completo"),
            ], limit=1)

            if not complete_status:
                raise UserError(
                    _("No se encontró el estado de proyecto 'Completo'.")
                )

            if project.project_status != complete_status:
                continue

            # -----------------------------------------------------
            # Comprobar tareas del proyecto
            # -----------------------------------------------------

            tasks = self.env["project.task"].sudo().search([
                ("project_id", "=", project.id),
                ("active", "=", True),
            ])

            if not tasks:
                continue

            # Todas tienen que estar realmente HECHAS
            all_done = all(
                task.state == "1_done"
                for task in tasks
            )

            if not all_done:
                continue

            # -----------------------------------------------------
            # Debe haber al menos un presupuesto asociado
            # -----------------------------------------------------

            if not project.serviflow_sale_order_ids:
                raise UserError(
                    _(
                        "El proyecto está completo, pero no tiene "
                        "ningún presupuesto asociado."
                    )
                )

            # -----------------------------------------------------
            # Evitar una segunda revisión de la misma ronda
            # -----------------------------------------------------

            pending_reviews = self.env["serviflow.task"].sudo().search_count([
                ("project_id", "=", project.id),
                ("task_type", "=", "review"),
                ("review_result", "=", "pending"),
                ("state", "=", "pending"),
            ])

            if pending_reviews:
                continue

            # -----------------------------------------------------
            # Cerrar fase técnica Serviflow
            # -----------------------------------------------------

            if serviflow_task.state != "done":
                serviflow_task.sudo().write({
                    "state": "done",
                    "completed_at": fields.Datetime.now(),
                })

            # -----------------------------------------------------
            # Crear ronda de revisión
            # -----------------------------------------------------

            serviflow_task._create_review_tasks()

            # -----------------------------------------------------
            # Trazabilidad
            # -----------------------------------------------------

            project.message_post(
                body=(
                    "<b>Proyecto enviado a revisión interna.</b><br/>"
                    "El proyecto está en estado <b>Completo</b> "
                    "y todas sus tareas están marcadas como "
                    "<b>Hecho</b>."
                )
            )
            
    def write(self, vals):
        res = super().write(vals)

        if "project_status" in vals:
            self._serviflow_check_tasks_completion()

        return res