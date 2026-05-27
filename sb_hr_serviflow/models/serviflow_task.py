from odoo import models, fields, _
from odoo.exceptions import UserError


class ServiflowTask(models.Model):
    _name = "serviflow.task"
    _description = "Solicitud Serviflow"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Nombre",
        required=True,
        tracking=True,
    )

    opportunity_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad",
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("accepted", "Aceptada"),
            ("done", "Hecha"),
            ("cancelled", "Cancelada"),
        ],
        string="Estado",
        default="pending",
        required=True,
        tracking=True,
    )

    assigned_user_id = fields.Many2one(
        "res.users",
        string="Usuario asignado",
        tracking=True,
    )

    accepted_user_id = fields.Many2one(
        "res.users",
        string="Aceptada por",
        tracking=True,
    )

    note = fields.Text(
        string="Notas",
    )
    
    reassign_user_id = fields.Many2one(
        "res.users",
        string="Reasignar a",
        domain=lambda self: [
            ("groups_id", "in", [self.env.ref("sb_hr_serviflow.group_serviflow_office_tech").id])
        ],
    )
    
    task_type = fields.Selection(
        [
            ("budget", "Presupuesto técnico"),
            ("review", "Revisión"),
        ],
        string="Tipo de solicitud",
        default="budget",
        required=True,
        tracking=True,
    )

    review_result = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("approved", "Aprobado"),
            ("rejected", "Rechazado"),
        ],
        string="Resultado revisión",
        default="pending",
        tracking=True,
    )

    def action_accept(self):
        for task in self:

            if task.state != "pending":
                continue

            task.write({
                "state": "accepted",
                "accepted_user_id": self.env.user.id,
                "assigned_user_id": self.env.user.id,
            })

            # asignar oportunidad CRM
            task.opportunity_id.write({
                "user_id": self.env.user.id,
            })

            task.message_post(
                body=f"Solicitud aceptada por {self.env.user.name}"
            )

    def action_done(self):
        for task in self:

            if task.state != "accepted":
                raise UserError(f"Estado actual: {task.state}. Debe estar en accepted.")

            if task.accepted_user_id != self.env.user:
                raise UserError(
                    "Solo el usuario que aceptó la solicitud puede marcarla como hecha."
                )

            task.write({
                "state": "done",
            })

            done_stage = self.env["crm.stage"].search([
                ("name", "=", "Presupuestado")
            ], limit=1)

            if not done_stage:
                raise UserError("No se encontró la etapa Presupuestado.")

            task.opportunity_id.write({
                "stage_id": done_stage.id,
            })
            
            task._create_review_tasks()

    def action_cancel(self):
        for task in self:
            task.write({
                "state": "cancelled",
            })

    def action_reassign_to_me(self):
        for task in self:
            if task.state not in ("pending", "accepted"):
                raise UserError(_("Solo se pueden reasignar solicitudes pendientes o aceptadas."))

            task.write({
                "state": "accepted",
                "assigned_user_id": self.env.user.id,
                "accepted_user_id": self.env.user.id,
            })

            task.opportunity_id.write({
                "user_id": self.env.user.id,
            })
            
    def action_reassign(self):
        for task in self:
            if not task.reassign_user_id:
                raise UserError("Selecciona un usuario para reasignar.")

            task.write({
                "state": "accepted",
                "assigned_user_id": task.reassign_user_id.id,
                "accepted_user_id": task.reassign_user_id.id,
            })

            task.opportunity_id.write({
                "user_id": task.reassign_user_id.id,
            })

            task.message_post(
                body=f"Solicitud reasignada a {task.reassign_user_id.name} por {self.env.user.name}"
            )

            task.reassign_user_id = False
            
    def _create_review_tasks(self):
        for task in self:
            if task.task_type != "budget":
                continue

            existing_reviews = self.env["serviflow.task"].search_count([
                ("opportunity_id", "=", task.opportunity_id.id),
                ("task_type", "=", "review"),
                ("state", "in", ["pending", "accepted"]),
            ])

            if existing_reviews:
                continue

            reviewers = self.env["serviflow.reviewer.config"].sudo().search([
                ("active", "=", True),
            ])

            if not reviewers:
                raise UserError("No hay revisores configurados en Serviflow.")

            for reviewer in reviewers:
                self.env["serviflow.task"].sudo().create({
                    "name": f"{reviewer.name} - {task.opportunity_id.name}",
                    "opportunity_id": task.opportunity_id.id,
                    "task_type": "review",
                    "assigned_user_id": reviewer.user_id.id,
                    "accepted_user_id": reviewer.user_id.id,
                    "state": "accepted",
                    "note": f"Revisión asignada a {reviewer.name}.",
                })