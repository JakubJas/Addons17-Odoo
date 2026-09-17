from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = "project.task"

    is_serviflow_budget_task = fields.Boolean(
        string="Tarea de presupuesto Serviflow",
        compute="_compute_serviflow_data",
    )

    serviflow_sale_order_id = fields.Many2one(
        "sale.order",
        string="Presupuesto Serviflow",
        compute="_compute_serviflow_data",
    )

    def _compute_serviflow_data(self):
        ServiflowTask = self.env["serviflow.task"].sudo()

        for task in self:
            sf_task = ServiflowTask.search([
                ("project_task_id", "=", task.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            task.is_serviflow_budget_task = bool(sf_task)

            task.serviflow_sale_order_id = (
                sf_task.sale_order_id.id
                if sf_task and sf_task.sale_order_id
                else False
            )

    def _get_serviflow_budget_task(self):
        self.ensure_one()

        sf_task = self.env["serviflow.task"].sudo().search([
            ("project_task_id", "=", self.id),
            ("task_type", "=", "budget"),
        ], order="create_date desc", limit=1)

        if not sf_task:
            raise UserError(
                _("Esta tarea no está vinculada a una solicitud de presupuesto de Serviflow.")
            )

        return sf_task

    def action_serviflow_quotation(self):
        self.ensure_one()

        sf_task = self._get_serviflow_budget_task()

        # -----------------------------------------------------
        # Si ya existe presupuesto -> abrirlo
        # -----------------------------------------------------

        if sf_task.sale_order_id:
            quotation = sf_task.sale_order_id

            return {
                "type": "ir.actions.act_window",
                "name": quotation.name,
                "res_model": "sale.order",
                "res_id": quotation.id,
                "views": [[False, "form"]],
                "view_mode": "form",
                "target": "current",
            }

        # -----------------------------------------------------
        # Crear presupuesto
        # -----------------------------------------------------

        lead = sf_task.opportunity_id

        if not lead:
            raise UserError(
                _("No existe una oportunidad CRM vinculada.")
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

        sf_task.sudo().write({
            "sale_order_id": quotation.id,
        })

        self.message_post(
            body=(
                f"Presupuesto <b>{quotation.name}</b> "
                "creado desde esta tarea mediante Serviflow."
            )
        )

        sf_task.message_post(
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