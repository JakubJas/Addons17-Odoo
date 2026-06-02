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
    
    review_round = fields.Integer(
        string="Ronda de revisión",
        default=1,
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

            last_review = self.env["serviflow.task"].search([
                ("opportunity_id", "=", task.opportunity_id.id),
                ("task_type", "=", "review"),
            ], order="review_round desc", limit=1)

            next_round = (last_review.review_round or 0) + 1 if last_review else 1

            existing_same_round = self.env["serviflow.task"].search_count([
                ("opportunity_id", "=", task.opportunity_id.id),
                ("task_type", "=", "review"),
                ("review_round", "=", next_round),
            ])

            if existing_same_round:
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
                    "review_round": next_round,
                    "assigned_user_id": reviewer.user_id.id,
                    "accepted_user_id": False,
                    "state": "pending",
                    "review_result": "pending",
                    "note": f"Revisión asignada a {reviewer.name}.",
                })
                
    def action_review_approve(self):
        for task in self:
            if task.task_type != "review":
                raise UserError("Esta solicitud no es una revisión.")

            if task.assigned_user_id != self.env.user:
                raise UserError("Solo el revisor asignado puede aprobar esta revisión.")

            if task.review_result != "pending":
                raise UserError("Esta revisión ya fue procesada.")

            task.write({
                "review_result": "approved",
                "state": "done",
                "accepted_user_id": self.env.user.id,
            })

            task.message_post(
                body=f"Revisión aprobada por {self.env.user.name}"
            )

            task._check_all_reviews_done()


    def action_review_reject(self):
        for task in self:
            if task.task_type != "review":
                raise UserError("Esta solicitud no es una revisión.")

            if task.assigned_user_id != self.env.user:
                raise UserError("Solo el revisor asignado puede rechazar esta revisión.")

            if task.review_result != "pending":
                raise UserError("Esta revisión ya fue procesada.")

            task.write({
                "review_result": "rejected",
                "state": "done",
                "accepted_user_id": self.env.user.id,
            })

            task.message_post(
                body=f"Revisión rechazada por {self.env.user.name}"
            )

            task._send_back_to_technical()
            
    def _check_all_reviews_done(self):
        for task in self:
            opportunity = task.opportunity_id

            last_round_review = self.env["serviflow.task"].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
            ], order="review_round desc", limit=1)

            if not last_round_review:
                return

            reviews = self.env["serviflow.task"].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
                ("review_round", "=", last_round_review.review_round),
            ])

            if not reviews:
                return

            if any(review.review_result == "rejected" for review in reviews):
                return

            if all(review.review_result == "approved" for review in reviews):
                approved_stage = self.env["crm.stage"].search([
                    ("name", "=", "Aprobado")
                ], limit=1)

                if approved_stage:
                    opportunity.write({
                        "stage_id": approved_stage.id,
                    })


    def _send_back_to_technical(self):
        for task in self:
            opportunity = task.opportunity_id

            technical_stage = self.env["crm.stage"].search([
                ("name", "=", "Solicitado Presupuesto Técnico")
            ], limit=1)

            if technical_stage:
                opportunity.write({
                    "stage_id": technical_stage.id,
                })

            original_budget_task = self.env["serviflow.task"].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "budget"),
                ("state", "=", "done"),
            ], order="create_date desc", limit=1)

            assigned_user = original_budget_task.accepted_user_id or original_budget_task.assigned_user_id
            
            current_round = task.review_round

            open_reviews = self.env["serviflow.task"].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
                ("review_round", "=", current_round),
                ("state", "in", ["pending", "accepted"]),
            ])

            open_reviews.write({
                "state": "cancelled",
            })

            self.env["serviflow.task"].sudo().create({
                "name": f"Corrección PPTO - {opportunity.name}",
                "opportunity_id": opportunity.id,
                "task_type": "budget",
                "state": "accepted" if assigned_user else "pending",
                "assigned_user_id": assigned_user.id if assigned_user else False,
                "accepted_user_id": assigned_user.id if assigned_user else False,
                "note": f"El presupuesto fue rechazado por {self.env.user.name}. Revisar y corregir.",
            })