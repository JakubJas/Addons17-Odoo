from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ProjectTask(models.Model):
    _inherit = "project.task"

    # =========================================================
    # DATOS SERVIFLOW
    # =========================================================

    is_serviflow_budget_task = fields.Boolean(
        string="Tarea de presupuesto Serviflow",
        compute="_compute_serviflow_data",
    )

    serviflow_opportunity_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad Serviflow",
        compute="_compute_serviflow_data",
    )

    serviflow_sale_order_ids = fields.Many2many(
        "sale.order",
        string="Presupuestos del proyecto",
        compute="_compute_serviflow_data",
        inverse="_inverse_serviflow_sale_order_ids",
        readonly=False,
    )

    serviflow_sale_order_count = fields.Integer(
        string="Nº Presupuestos",
        compute="_compute_serviflow_data",
    )
    
    serviflow_request_note = fields.Text(
        string="Indicaciones Serviflow",
        compute="_compute_serviflow_detail_data",
    )

    serviflow_priority_label = fields.Char(
        string="Prioridad",
        compute="_compute_serviflow_detail_data",
    )

    serviflow_requested_date_label = fields.Char(
        string="Fecha deseada",
        compute="_compute_serviflow_detail_data",
    )

    serviflow_last_rejection_reason = fields.Text(
        string="Último motivo de rechazo",
        compute="_compute_serviflow_detail_data",
    )

    serviflow_current_round = fields.Integer(
        string="Ronda actual",
        compute="_compute_serviflow_detail_data",
    )

    serviflow_has_rejection = fields.Boolean(
        string="Tiene rechazo",
        compute="_compute_serviflow_detail_data",
    )

    # =========================================================
    # COMPUTE
    # =========================================================

    @api.depends(
        "project_id",
        "project_id.serviflow_opportunity_id",
        "project_id.serviflow_sale_order_ids",
    )
    def _compute_serviflow_data(self):

        ServiflowTask = self.env["serviflow.task"].sudo()

        for task in self:

            task.is_serviflow_budget_task = False
            task.serviflow_opportunity_id = False
            task.serviflow_sale_order_ids = False
            task.serviflow_sale_order_count = 0

            if not task.project_id:
                continue

            sf_task = ServiflowTask.search([
                ("project_task_id", "=", task.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            if not sf_task:
                continue

            task.is_serviflow_budget_task = True

            task.serviflow_opportunity_id = (
                sf_task.opportunity_id
            )

            task.serviflow_sale_order_ids = (
                task.project_id.serviflow_sale_order_ids
            )

            task.serviflow_sale_order_count = len(
                task.project_id.serviflow_sale_order_ids
            )
            
    def _compute_serviflow_detail_data(self):
        ServiflowTask = self.env["serviflow.task"].sudo()

        for task in self:

            # -----------------------------------------------------
            # Valores por defecto
            # -----------------------------------------------------

            task.serviflow_request_note = False
            task.serviflow_priority_label = False
            task.serviflow_requested_date_label = False
            task.serviflow_last_rejection_reason = False
            task.serviflow_current_round = 0
            task.serviflow_has_rejection = False

            # -----------------------------------------------------
            # Buscar solicitud técnica principal
            # -----------------------------------------------------

            budget_task = ServiflowTask.search([
                ("project_task_id", "=", task.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            if not budget_task:
                continue

            # =====================================================
            # DATOS DE SOLICITUD
            # =====================================================

            note = budget_task.note or ""

            priority_label = False
            requested_date_label = False
            indications = False

            if note:
                indication_lines = []
                capture_indications = False

                for line in note.splitlines():

                    clean_line = line.strip()

                    if clean_line.startswith("PRIORIDAD:"):
                        priority_label = clean_line.replace(
                            "PRIORIDAD:",
                            "",
                            1,
                        ).strip()

                    elif clean_line.startswith("FECHA DESEADA:"):
                        requested_date_label = clean_line.replace(
                            "FECHA DESEADA:",
                            "",
                            1,
                        ).strip()

                    elif clean_line.startswith("INDICACIONES:"):
                        capture_indications = True

                    elif capture_indications:
                        indication_lines.append(line)

                indications = "\n".join(
                    indication_lines
                ).strip()

            task.serviflow_priority_label = priority_label
            task.serviflow_requested_date_label = requested_date_label
            task.serviflow_request_note = indications

            # =====================================================
            # ÚLTIMA RONDA REAL DEL PROYECTO
            # =====================================================

            last_review = ServiflowTask.search([
                ("project_id", "=", task.project_id.id),
                ("task_type", "=", "review"),
            ], order="review_round desc, create_date desc", limit=1)

            if not last_review:
                continue

            current_round = last_review.review_round or 0

            task.serviflow_current_round = current_round

            # =====================================================
            # REVISIONES DE LA ÚLTIMA RONDA
            # =====================================================

            current_reviews = ServiflowTask.search([
                ("project_id", "=", task.project_id.id),
                ("task_type", "=", "review"),
                ("review_round", "=", current_round),
            ])

            # =====================================================
            # ¿LA ÚLTIMA RONDA FUE RECHAZADA?
            # =====================================================

            rejected_review = current_reviews.filtered(
                lambda r: r.review_result == "rejected"
            )[:1]

            if rejected_review:
                task.serviflow_has_rejection = True

                task.serviflow_last_rejection_reason = (
                    rejected_review.rejection_reason
                    or "Sin motivo indicado."
                )

    # =========================================================
    # GUARDAR SELECTOR MÚLTIPLE EN EL PROYECTO
    # =========================================================

    def _inverse_serviflow_sale_order_ids(self):

        for task in self:

            if not task.project_id:
                continue

            if not task.is_serviflow_budget_task:
                continue

            task.project_id.sudo().write({
                "serviflow_sale_order_ids": [
                    (6, 0, task.serviflow_sale_order_ids.ids)
                ],
            })

            # Mantener compatibilidad con sale_order_id antiguo
            sf_task = self.env[
                "serviflow.task"
            ].sudo().search([
                ("project_task_id", "=", task.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            if sf_task:
                first_quotation = (
                    task.serviflow_sale_order_ids[:1]
                )

                sf_task.sudo().write({
                    "sale_order_id": (
                        first_quotation.id
                        if first_quotation
                        else False
                    )
                })

    # =========================================================
    # OBTENER SOLICITUD SERVIFLOW
    # =========================================================

    def _get_serviflow_budget_task(self):
        self.ensure_one()

        sf_task = self.env["serviflow.task"].sudo().search([
            ("project_task_id", "=", self.id),
            ("task_type", "=", "budget"),
        ], order="create_date desc", limit=1)

        if not sf_task:
            raise UserError(
                _(
                    "Esta tarea no está vinculada a una solicitud "
                    "de presupuesto de Serviflow."
                )
            )

        return sf_task

    # =========================================================
    # CREAR NUEVO PRESUPUESTO
    # =========================================================

    def action_serviflow_create_quotation(self):
        self.ensure_one()

        sf_task = self._get_serviflow_budget_task()

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

        # Añadirlo al proyecto
        self.project_id.sudo().write({
            "serviflow_sale_order_ids": [
                (4, quotation.id)
            ],
        })

        # Compatibilidad con código antiguo
        sf_task.sudo().write({
            "sale_order_id": quotation.id,
        })

        self.message_post(
            body=(
                f"Presupuesto <b>{quotation.name}</b> "
                "creado y asociado al proyecto."
            )
        )

        sf_task.message_post(
            body=(
                f"Presupuesto <b>{quotation.name}</b> "
                f"creado desde la tarea "
                f"<b>{self.name}</b>."
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

    # =========================================================
    # ABRIR PRESUPUESTOS
    # =========================================================

    def action_serviflow_open_quotations(self):
        self.ensure_one()

        quotations = (
            self.project_id.serviflow_sale_order_ids
        )

        if not quotations:
            raise UserError(
                _("Este proyecto todavía no tiene presupuestos asociados.")
            )

        # Uno -> directamente
        if len(quotations) == 1:
            quotation = quotations

            return {
                "type": "ir.actions.act_window",
                "name": quotation.name,
                "res_model": "sale.order",
                "res_id": quotation.id,
                "views": [[False, "form"]],
                "view_mode": "form",
                "target": "current",
            }

        # Varios -> listado
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
    # CAMBIO DE ESTADO DE TAREA
    # =========================================================

    def write(self, vals):
        res = super().write(vals)

        if "state" not in vals:
            return res

        projects = self.mapped("project_id")

        for project in projects:
            if project:
                project._serviflow_check_tasks_completion()

        return res
    