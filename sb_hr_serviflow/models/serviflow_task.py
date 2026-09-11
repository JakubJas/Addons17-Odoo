from odoo import api, models, fields, _
from odoo.exceptions import UserError


class ServiflowTask(models.Model):
    _name = "serviflow.task"
    _description = "Solicitud Serviflow"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    # =========================================================
    # CAMPOS
    # =========================================================

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
            (
                "groups_id",
                "in",
                [
                    self.env.ref(
                        "sb_hr_serviflow.group_serviflow_office_tech"
                    ).id
                ],
            )
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

    sale_order_id = fields.Many2one(
        "sale.order",
        string="Presupuesto",
        tracking=True,
        domain="[('opportunity_id', '=', opportunity_id)]",
    )

    # =========================================================
    # RECUPERAR / ASEGURAR PRESUPUESTO
    # =========================================================

    def _ensure_sale_order(self):
        """
        Garantiza que la tarea tenga un presupuesto asociado.

        Si sale_order_id está vacío, busca el último presupuesto
        vinculado a la misma oportunidad CRM y lo guarda en la tarea.
        """

        for task in self:

            if task.sale_order_id:
                continue

            if not task.opportunity_id:
                continue

            sale_order = self.env["sale.order"].search([
                ("opportunity_id", "=", task.opportunity_id.id),
            ], order="create_date desc", limit=1)

            if sale_order:
                task.sudo().write({
                    "sale_order_id": sale_order.id,
                })

        return True

    # =========================================================
    # ACEPTAR SOLICITUD
    # =========================================================

    def action_accept(self):
        for task in self:

            if task.task_type != "budget":
                raise UserError(
                    "Solo se pueden aceptar solicitudes de presupuesto técnico."
                )

            if task.state != "pending":
                raise UserError(
                    "Esta solicitud ya ha sido aceptada por otro usuario."
                )

            task.write({
                "state": "accepted",
                "accepted_user_id": self.env.user.id,
                "assigned_user_id": self.env.user.id,
            })

            task.opportunity_id.write({
                "user_id": self.env.user.id,
            })

            task._close_user_activities()

            task.message_post(
                body=f"Solicitud aceptada por {self.env.user.name}"
            )

        return True

    # =========================================================
    # MARCAR SOLICITUD COMO HECHA
    # =========================================================

    def action_done(self):
        for task in self:

            if task.state != "accepted":
                raise UserError(
                    f"Estado actual: {task.state}. Debe estar en accepted."
                )

            if task.accepted_user_id != self.env.user:
                raise UserError(
                    "Solo el usuario que aceptó la solicitud "
                    "puede marcarla como hecha."
                )

            # Recuperar presupuesto si todavía no está enlazado
            task._ensure_sale_order()

            if not task.sale_order_id:
                raise UserError(
                    "No hay ningún presupuesto vinculado a esta solicitud. "
                    "Crea el presupuesto antes de marcarla como hecha."
                )

            task.write({
                "state": "done",
            })

            task._close_user_activities()

            done_stage = self.env["crm.stage"].search([
                ("name", "=", "Presupuestado")
            ], limit=1)

            if not done_stage:
                raise UserError(
                    "No se encontró la etapa Presupuestado."
                )

            task.opportunity_id.write({
                "stage_id": done_stage.id,
            })

            task._create_review_tasks()

        return True

    # =========================================================
    # CANCELAR
    # =========================================================

    def action_cancel(self):
        for task in self:

            task.write({
                "state": "cancelled",
            })

        return True

    # =========================================================
    # REASIGNACIÓN
    # =========================================================

    def action_reassign_to_me(self):
        for task in self:

            if task.task_type != "budget":
                raise UserError(
                    "No se pueden reasignar tareas de revisión."
                )

            if task.state not in ("pending", "accepted"):
                raise UserError(
                    _(
                        "Solo se pueden reasignar solicitudes "
                        "pendientes o aceptadas."
                    )
                )

            task.write({
                "state": "accepted",
                "assigned_user_id": self.env.user.id,
                "accepted_user_id": self.env.user.id,
            })

            task.opportunity_id.write({
                "user_id": self.env.user.id,
            })

        return True

    def action_reassign(self):
        for task in self:

            if task.task_type != "budget":
                raise UserError(
                    "No se pueden reasignar tareas de revisión. "
                    "Cambia el revisor desde la configuración de Revisores."
                )

            if not task.reassign_user_id:
                raise UserError(
                    "Selecciona un usuario para reasignar."
                )

            task.write({
                "state": "accepted",
                "assigned_user_id": task.reassign_user_id.id,
                "accepted_user_id": task.reassign_user_id.id,
            })

            task.opportunity_id.write({
                "user_id": task.reassign_user_id.id,
            })

            task._close_user_activities()
            task._create_user_activity()

            task.message_post(
                body=(
                    f"Solicitud reasignada a "
                    f"{task.reassign_user_id.name} "
                    f"por {self.env.user.name}"
                )
            )

            task.reassign_user_id = False

        return True

    # =========================================================
    # CREAR / ABRIR PRESUPUESTO
    # =========================================================

    def action_create_quotation(self):
        self.ensure_one()

        if self.task_type != "budget":
            raise UserError(
                "Solo se puede crear un presupuesto "
                "desde una solicitud técnica."
            )

        # Primero comprobar si ya existe uno enlazado
        self._ensure_sale_order()

        if self.sale_order_id:
            return {
                "type": "ir.actions.act_window",
                "res_model": "sale.order",
                "res_id": self.sale_order_id.id,
                "view_mode": "form",
                "target": "current",
            }

        lead = self.opportunity_id

        if not lead.partner_id:
            raise UserError(
                "La oportunidad debe tener un cliente asignado "
                "antes de crear el presupuesto."
            )

        quotation = self.env["sale.order"].create({
            "partner_id": lead.partner_id.id,
            "opportunity_id": lead.id,
            "origin": lead.name,
        })

        self.write({
            "sale_order_id": quotation.id,
        })

        self.message_post(
            body=f"Presupuesto {quotation.name} creado y vinculado a la solicitud."
        )

        return {
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "res_id": quotation.id,
            "view_mode": "form",
            "target": "current",
        }

    # =========================================================
    # CREACIÓN DE REVISIONES
    # =========================================================

    def _create_review_tasks(self):
        for task in self:

            if task.task_type != "budget":
                continue

            # Asegurar presupuesto
            task._ensure_sale_order()

            if not task.sale_order_id:
                raise UserError(
                    "No se encontró ningún presupuesto "
                    "vinculado a esta solicitud."
                )

            sale_order = task.sale_order_id

            # Buscar última ronda
            last_review = self.env["serviflow.task"].search([
                ("opportunity_id", "=", task.opportunity_id.id),
                ("task_type", "=", "review"),
            ], order="review_round desc", limit=1)

            next_round = (
                (last_review.review_round or 0) + 1
                if last_review
                else 1
            )

            # Evitar duplicados
            existing_same_round = self.env[
                "serviflow.task"
            ].search_count([
                ("opportunity_id", "=", task.opportunity_id.id),
                ("task_type", "=", "review"),
                ("review_round", "=", next_round),
            ])

            if existing_same_round:
                continue

            reviewers = self.env[
                "serviflow.reviewer.config"
            ].sudo().search([
                ("active", "=", True),
            ])

            if not reviewers:
                raise UserError(
                    "No hay revisores configurados en Serviflow."
                )

            for reviewer in reviewers:

                review_task = self.env[
                    "serviflow.task"
                ].sudo().create({

                    "name": (
                        f"{reviewer.name} - "
                        f"{task.opportunity_id.name}"
                    ),

                    "opportunity_id": task.opportunity_id.id,

                    # El mismo presupuesto de la tarea técnica
                    "sale_order_id": sale_order.id,

                    "task_type": "review",
                    "review_round": next_round,

                    "assigned_user_id": reviewer.user_id.id,
                    "accepted_user_id": False,

                    "state": "pending",
                    "review_result": "pending",

                    "note": (
                        f"Revisión asignada a "
                        f"{reviewer.name}."
                    ),
                })

                review_task._create_user_activity()

    # =========================================================
    # APROBAR REVISIÓN
    # =========================================================

    def action_review_approve(self):
        for task in self:

            if task.task_type != "review":
                raise UserError(
                    "Esta solicitud no es una revisión."
                )

            if task.assigned_user_id != self.env.user:
                raise UserError(
                    "Solo el revisor asignado "
                    "puede aprobar esta revisión."
                )

            if task.review_result != "pending":
                raise UserError(
                    "Esta revisión ya fue procesada."
                )

            # Importante para revisiones antiguas
            task._ensure_sale_order()

            task.write({
                "review_result": "approved",
                "state": "done",
                "accepted_user_id": self.env.user.id,
            })

            task._close_user_activities()

            task.message_post(
                body=f"Revisión aprobada por {self.env.user.name}"
            )

            task._check_all_reviews_done()

        return True

    # =========================================================
    # RECHAZAR REVISIÓN
    # =========================================================

    def action_review_reject(self):
        for task in self:

            if task.task_type != "review":
                raise UserError(
                    "Esta solicitud no es una revisión."
                )

            if task.assigned_user_id != self.env.user:
                raise UserError(
                    "Solo el revisor asignado "
                    "puede rechazar esta revisión."
                )

            if task.review_result != "pending":
                raise UserError(
                    "Esta revisión ya fue procesada."
                )

            # Importante para revisiones antiguas
            task._ensure_sale_order()

            task.write({
                "review_result": "rejected",
                "state": "done",
                "accepted_user_id": self.env.user.id,
            })

            task._close_user_activities()

            task.message_post(
                body=f"Revisión rechazada por {self.env.user.name}"
            )

            task._send_back_to_technical()

        return True

    # =========================================================
    # COMPROBAR REVISIONES
    # =========================================================

    def _check_all_reviews_done(self):
        for task in self:

            opportunity = task.opportunity_id

            last_round_review = self.env[
                "serviflow.task"
            ].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
            ], order="review_round desc", limit=1)

            if not last_round_review:
                return

            reviews = self.env[
                "serviflow.task"
            ].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
                (
                    "review_round",
                    "=",
                    last_round_review.review_round,
                ),
            ])

            if any(
                review.review_result == "rejected"
                for review in reviews
            ):
                return

            if (
                not reviews
                or any(
                    review.review_result == "pending"
                    for review in reviews
                )
            ):
                return

            approved_stage = self.env["crm.stage"].search([
                ("name", "=", "Aprobado")
            ], limit=1)

            if not approved_stage:
                raise UserError(
                    "No se encontró la etapa Aprobado."
                )

            opportunity.write({
                "stage_id": approved_stage.id,
            })

            opportunity.message_post(
                body=(
                    "Presupuesto aprobado tras completar "
                    f"la ronda {last_round_review.review_round} "
                    "de revisión."
                )
            )

    # =========================================================
    # DEVOLVER A TÉCNICO / CORRECCIÓN
    # =========================================================

    def _send_back_to_technical(self, rejection_reason=False):
        for task in self:

            opportunity = task.opportunity_id

            # Recuperar presupuesto incluso en revisiones antiguas
            task._ensure_sale_order()

            sale_order = task.sale_order_id

            technical_stage = self.env[
                "crm.stage"
            ].search([
                ("name", "=", "Solicitado Presupuesto Técnico")
            ], limit=1)

            if technical_stage:
                opportunity.write({
                    "stage_id": technical_stage.id,
                })

            original_budget_task = self.env[
                "serviflow.task"
            ].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "budget"),
                ("state", "=", "done"),
            ], order="create_date desc", limit=1)

            assigned_user = (
                original_budget_task.accepted_user_id
                or original_budget_task.assigned_user_id
            )

            current_round = task.review_round

            open_reviews = self.env[
                "serviflow.task"
            ].search([
                ("opportunity_id", "=", opportunity.id),
                ("task_type", "=", "review"),
                ("review_round", "=", current_round),
                ("state", "in", ["pending", "accepted"]),
            ])

            open_reviews.write({
                "state": "cancelled",
            })

            correction_task = self.env[
                "serviflow.task"
            ].sudo().create({

                "name": (
                    f"Corrección PPTO - "
                    f"{opportunity.name}"
                ),

                "opportunity_id": opportunity.id,

                # Mantener presupuesto
                "sale_order_id": (
                    sale_order.id
                    if sale_order
                    else False
                ),

                "task_type": "budget",

                "state": (
                    "accepted"
                    if assigned_user
                    else "pending"
                ),

                "assigned_user_id": (
                    assigned_user.id
                    if assigned_user
                    else False
                ),

                "accepted_user_id": (
                    assigned_user.id
                    if assigned_user
                    else False
                ),

                "note": (
                    f"Presupuesto rechazado por {self.env.user.name}."
                    + (
                        f"\n\nMOTIVO DEL RECHAZO:\n{rejection_reason}"
                        if rejection_reason
                        else ""
                    )
                ),
            })

            if assigned_user:
                correction_task._create_user_activity()
            else:
                correction_task._create_group_activities()

    # =========================================================
    # ACTIVIDAD PARA USUARIO
    # =========================================================

    def _create_user_activity(self):

        activity_type = self.env.ref(
            "mail.mail_activity_data_todo",
            raise_if_not_found=False
        )

        model_id = self.env[
            "ir.model"
        ]._get_id("serviflow.task")

        for task in self:

            if not activity_type:
                continue

            if not task.assigned_user_id:
                continue

            existing = self.env[
                "mail.activity"
            ].sudo().search_count([
                ("res_model", "=", "serviflow.task"),
                ("res_id", "=", task.id),
                ("user_id", "=", task.assigned_user_id.id),
            ])

            if existing:
                continue

            self.env["mail.activity"].sudo().create({

                "res_model_id": model_id,
                "res_id": task.id,

                "user_id": task.assigned_user_id.id,

                "activity_type_id": activity_type.id,

                "summary": task._get_activity_summary(),

                "note": task.note or "",

                "date_deadline": fields.Date.today(),
            })

    # =========================================================
    # ACTIVIDAD PARA GRUPO TÉCNICO
    # =========================================================

    def _create_group_activities(self):

        activity_type = self.env.ref(
            "mail.mail_activity_data_todo",
            raise_if_not_found=False
        )

        group = self.env.ref(
            "sb_hr_serviflow.group_serviflow_office_tech",
            raise_if_not_found=False
        )

        model_id = self.env[
            "ir.model"
        ]._get_id("serviflow.task")

        for task in self:

            if not activity_type or not group:
                continue

            for user in group.users:

                existing = self.env[
                    "mail.activity"
                ].sudo().search_count([
                    ("res_model", "=", "serviflow.task"),
                    ("res_id", "=", task.id),
                    ("user_id", "=", user.id),
                ])

                if existing:
                    continue

                self.env["mail.activity"].sudo().create({

                    "res_model_id": model_id,
                    "res_id": task.id,

                    "user_id": user.id,

                    "activity_type_id": activity_type.id,

                    "summary": task._get_activity_summary(),

                    "note": task.note or "",

                    "date_deadline": fields.Date.today(),
                })

    # =========================================================
    # CERRAR ACTIVIDADES
    # =========================================================

    def _close_user_activities(self):

        for task in self:

            activities = self.env[
                "mail.activity"
            ].sudo().search([
                ("res_model", "=", "serviflow.task"),
                ("res_id", "=", task.id),
            ])

            if activities:
                activities.action_feedback(
                    feedback="Gestionado desde Serviflow"
                )

    # =========================================================
    # TEXTO DE ACTIVIDAD
    # =========================================================

    def _get_activity_summary(self):
        self.ensure_one()

        if (
            self.task_type == "budget"
            and self.state == "pending"
        ):
            return (
                f"PPTO técnico: "
                f"{self.opportunity_id.name}"
            )

        if (
            self.task_type == "budget"
            and self.state == "accepted"
        ):
            return (
                f"Corrección/Trabajo PPTO: "
                f"{self.opportunity_id.name}"
            )

        if self.task_type == "review":
            return (
                f"Revisión presupuesto: "
                f"{self.opportunity_id.name}"
            )

        return self.name

    # =========================================================
    # SYSTRAY - SOLICITUDES
    # =========================================================

    @api.model
    def get_my_pending_systray_tasks(self):

        activities = self.env[
            "mail.activity"
        ].sudo().search([
            ("res_model", "=", "serviflow.task"),
            ("user_id", "=", self.env.user.id),
        ])

        task_ids = activities.mapped("res_id")

        tasks = self.search([
            ("id", "in", task_ids),
            ("task_type", "=", "budget"),
            ("state", "=", "pending"),
        ])

        return [{
            "id": task.id,
            "name": task.name,
            "opportunity": (
                task.opportunity_id.name or ""
            ),
        } for task in tasks]

    # =========================================================
    # SYSTRAY - REVISIONES
    # =========================================================

    @api.model
    def get_my_pending_systray_reviews(self):

        activities = self.env[
            "mail.activity"
        ].sudo().search([
            ("res_model", "=", "serviflow.task"),
            ("user_id", "=", self.env.user.id),
        ])

        task_ids = activities.mapped("res_id")

        reviews = self.sudo().search([
            ("id", "in", task_ids),
            ("task_type", "=", "review"),
            ("assigned_user_id", "=", self.env.user.id),
            ("review_result", "=", "pending"),
            ("state", "=", "pending"),
        ])

        # Aprovechamos para recuperar presupuesto
        # en revisiones antiguas.
        reviews._ensure_sale_order()

        return [{
            "id": review.id,
            "name": review.name,
            "opportunity": (
                review.opportunity_id.name or ""
            ),
            "round": review.review_round,
        } for review in reviews]
        
    def action_open_reject_wizard(self):
        self.ensure_one()

        if self.task_type != "review":
            raise UserError(
                "Esta tarea no es una revisión."
            )

        if self.assigned_user_id != self.env.user:
            raise UserError(
                "Solo el revisor asignado puede rechazar esta revisión."
            )

        if self.review_result != "pending":
            raise UserError(
                "Esta revisión ya fue procesada."
            )

        return {
            "type": "ir.actions.act_window",
            "name": "Rechazar revisión",
            "res_model": "serviflow.reject.wizard",
            "views": [[False, "form"]],
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_task_id": self.id,
            },
        }