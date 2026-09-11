from odoo import models, fields, _
from odoo.exceptions import UserError


class ServiflowRejectWizard(models.TransientModel):
    _name = "serviflow.reject.wizard"
    _description = "Motivo de rechazo Serviflow"

    task_id = fields.Many2one(
        "serviflow.task",
        string="Revisión",
        required=True,
        readonly=True,
    )

    rejection_reason = fields.Text(
        string="Motivo del rechazo",
        required=True,
    )

    def action_confirm_reject(self):
        self.ensure_one()

        if not self.rejection_reason or not self.rejection_reason.strip():
            raise UserError(
                _("Debes indicar el motivo del rechazo.")
            )

        task = self.task_id

        if task.task_type != "review":
            raise UserError(
                _("Esta tarea no es una revisión.")
            )

        if task.assigned_user_id != self.env.user:
            raise UserError(
                _("Solo el revisor asignado puede rechazar esta revisión.")
            )

        if task.review_result != "pending":
            raise UserError(
                _("Esta revisión ya fue procesada.")
            )

        task._ensure_sale_order()

        task.write({
            "review_result": "rejected",
            "state": "done",
            "accepted_user_id": self.env.user.id,
        })

        task._close_user_activities()

        task.message_post(
            body=(
                f"<b>Revisión rechazada por {self.env.user.name}</b><br/>"
                f"<b>Motivo:</b><br/>{self.rejection_reason}"
            )
        )

        task._send_back_to_technical(
            rejection_reason=self.rejection_reason.strip()
        )

        return {
            "type": "ir.actions.act_window_close",
        }