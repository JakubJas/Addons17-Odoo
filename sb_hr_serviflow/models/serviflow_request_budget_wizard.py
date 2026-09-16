from odoo import models, fields, _
from odoo.exceptions import UserError


class ServiflowRequestBudgetWizard(models.TransientModel):
    _name = "serviflow.request.budget.wizard"
    _description = "Solicitar Presupuesto Técnico"

    opportunity_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad",
        required=True,
        readonly=True,
    )

    technical_notes = fields.Text(
        string="Indicaciones para Oficina Técnica",
        required=True,
    )

    priority = fields.Selection(
        [
            ("0", "Normal"),
            ("1", "Baja"),
            ("2", "Alta"),
            ("3", "Muy alta"),
        ],
        string="Prioridad",
        default="0",
        required=True,
    )

    requested_date = fields.Date(
        string="Fecha deseada",
    )

    def action_confirm(self):
        self.ensure_one()

        if not self.technical_notes or not self.technical_notes.strip():
            raise UserError(
                _("Debes indicar las instrucciones para Oficina Técnica.")
            )

        lead = self.opportunity_id

        # ---------------------------------------------------------
        # Buscar etapa CRM
        # ---------------------------------------------------------

        stage = self.env["crm.stage"].search([
            ("name", "=", "Solicitado Presupuesto Técnico")
        ], limit=1)

        if not stage:
            raise UserError(
                _("No se encontró la etapa 'Solicitado Presupuesto Técnico'.")
            )

        # ---------------------------------------------------------
        # Preparar datos del popup
        # ---------------------------------------------------------

        priority_labels = {
            "0": "Normal",
            "1": "Baja",
            "2": "Alta",
            "3": "Muy alta",
        }

        priority_name = priority_labels.get(
            self.priority,
            "Normal"
        )

        requested_date_text = (
            self.requested_date.strftime("%d/%m/%Y")
            if self.requested_date
            else "Sin fecha indicada"
        )

        serviflow_note = (
            f"PRIORIDAD: {priority_name}\n"
            f"FECHA DESEADA: {requested_date_text}\n\n"
            f"INDICACIONES:\n"
            f"{self.technical_notes.strip()}"
        )

        # ---------------------------------------------------------
        # Comprobar si ya existe una solicitud activa
        # ---------------------------------------------------------

        existing = self.env["serviflow.task"].search([
            ("opportunity_id", "=", lead.id),
            ("task_type", "=", "budget"),
            ("state", "in", ["pending", "accepted"]),
        ], limit=1)

        if existing:
            raise UserError(
                _("Ya existe una solicitud de presupuesto técnico activa para esta oportunidad.")
            )

        # ---------------------------------------------------------
        # Buscar estado inicial del proyecto
        # ---------------------------------------------------------

        pending_status = self.env["project.status"].sudo().search([
            ("name", "=", "Pendiente"),
        ], limit=1)

        if not pending_status:
            raise UserError(
                _("No se encontró el estado de proyecto 'Pendiente'.")
            )

        # ---------------------------------------------------------
        # Crear proyecto
        # Solo nombre + estado.
        # ---------------------------------------------------------

        project = self.env["project.project"].sudo().create({
            "name": lead.name,
            "project_status": pending_status.id,
        })

        # ---------------------------------------------------------
        # Crear tarea principal
        # ---------------------------------------------------------

        project_task = self.env["project.task"].sudo().create({
            "name": "Preparar presupuesto técnico",
            "project_id": project.id,
        })

        # ---------------------------------------------------------
        # Crear solicitud Serviflow
        # ---------------------------------------------------------

        task = self.env["serviflow.task"].sudo().create({
            "name": f"PPTO - {lead.name}",
            "opportunity_id": lead.id,
            "task_type": "budget",
            "state": "pending",
            "note": serviflow_note,

            "project_id": project.id,
            "project_task_id": project_task.id,

            "requested_by_user_id": self.env.user.id,
            "requested_at": fields.Datetime.now(),
        })

        # ---------------------------------------------------------
        # Crear actividades para Oficina Técnica
        # ---------------------------------------------------------

        task._create_group_activities()

        # ---------------------------------------------------------
        # Cambiar etapa CRM
        # ---------------------------------------------------------

        lead.with_context(
            serviflow_from_wizard=True
        ).write({
            "stage_id": stage.id,
        })

        # ---------------------------------------------------------
        # Registrar trazabilidad en CRM
        # ---------------------------------------------------------

        lead.message_post(
            body=(
                "<b>Solicitud de presupuesto técnico creada</b><br/>"
                f"<b>Prioridad:</b> {priority_name}<br/>"
                f"<b>Fecha deseada:</b> {requested_date_text}<br/>"
                f"<b>Indicaciones:</b> {self.technical_notes}"
            )
        )

        return {
            "type": "ir.actions.act_window_close",
        }