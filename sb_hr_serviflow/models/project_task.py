from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_serviflow_budget_task = fields.Boolean(
        string="Tarea de presupuesto Serviflow",
        compute="_compute_serviflow_budget_data",
    )

    serviflow_sale_order_id = fields.Many2one(
        "sale.order",
        string="Presupuesto",
        compute="_compute_serviflow_budget_data",
    )

    @api.depends()
    def _compute_serviflow_budget_data(self):
        ServiflowTask = self.env["serviflow.task"].sudo()

        for task in self:
            serviflow_task = ServiflowTask.search([
                ("project_task_id", "=", task.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            task.is_serviflow_budget_task = bool(serviflow_task)
            task.serviflow_sale_order_id = (
                serviflow_task.sale_order_id
                if serviflow_task
                else False
            )

    def _get_serviflow_budget_task(self):
        self.ensure_one()

        serviflow_task = self.env["serviflow.task"].sudo().search([
            ("project_task_id", "=", self.id),
            ("task_type", "=", "budget"),
        ], order="create_date desc", limit=1)

        if not serviflow_task:
            raise UserError(
                _(
                    "Esta tarea no está vinculada a una solicitud "
                    "de presupuesto de Serviflow."
                )
            )

        return serviflow_task

    def action_serviflow_create_quotation(self):
        self.ensure_one()

        serviflow_task = self._get_serviflow_budget_task()

        # Si ya existe, simplemente abrirlo
        if serviflow_task.sale_order_id:
            return {
                "type": "ir.actions.act_window",
                "name": serviflow_task.sale_order_id.name,
                "res_model": "sale.order",
                "res_id": serviflow_task.sale_order_id.id,
                "views": [[False, "form"]],
                "view_mode": "form",
                "target": "current",
            }

        lead = serviflow_task.opportunity_id

        if not lead:
            raise UserError(
                _("No se encontró la oportunidad CRM asociada.")
            )

        if not lead.partner_id:
            raise UserError(
                _(
                    "La oportunidad debe tener un cliente asignado "
                    "antes de crear el presupuesto."
                )
            )

        quotation = self.env["sale.order"].sudo().create({
            "partner_id": lead.partner_id.id,
            "opportunity_id": lead.id,
            "origin": lead.name,
        })

        serviflow_task.sudo().write({
            "sale_order_id": quotation.id,
        })

        self.message_post(
            body=(
                f"Presupuesto <b>{quotation.name}</b> creado "
                "desde la tarea mediante Serviflow."
            )
        )

        serviflow_task.message_post(
            body=(
                f"Presupuesto <b>{quotation.name}</b> "
                f"vinculado a la tarea <b>{self.name}</b>."
            )
        )

        return {
            "type": "ir.actions.act_window",
            "name": quotation.name,
            "res_model": "sale.order",
            "res_id": quotation.id,
            "views": [[False, "form"]],
            "view_mode": "form",
            "target": "current",
        }

    def write(self, vals):
        res = super().write(vals)

        # Más adelante utilizaremos aquí el cambio a "Hecho"
        # para comprobar si todas las tareas del proyecto
        # están terminadas y lanzar la revisión.
        return res