from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = "project.task"

    def write(self, vals):
        res = super().write(vals)

        if "stage_id" not in vals:
            return res

        for project_task in self:

            if not project_task.stage_id:
                continue

            # Solo nos interesa cuando entra en "En revisión"
            if project_task.stage_id.name != "En revisión":
                continue

            # Buscar la solicitud Serviflow vinculada
            serviflow_task = self.env["serviflow.task"].sudo().search([
                ("project_task_id", "=", project_task.id),
                ("task_type", "=", "budget"),
                ("state", "in", ["pending", "accepted", "done"]),
            ], order="create_date desc", limit=1)

            if not serviflow_task:
                continue

            # Si ya estaba marcada como realizada, no pasa nada.
            # Si estaba aceptada, la cerramos ahora.
            if serviflow_task.state == "accepted":
                serviflow_task.write({
                    "state": "done",
                    "completed_at": fields.Datetime.now(),
                })

            # Generar ronda de revisión
            serviflow_task._create_review_tasks()

            # Trazabilidad
            serviflow_task.message_post(
                body=(
                    f"La tarea de proyecto "
                    f"<b>{project_task.name}</b> "
                    f"ha pasado a <b>En revisión</b>."
                )
            )

            project_task.message_post(
                body=(
                    "Trabajo técnico enviado a revisión interna "
                    "mediante Serviflow."
                )
            )

        return res