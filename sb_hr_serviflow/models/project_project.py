from odoo import fields, models, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    def _serviflow_check_tasks_completion(self):
        """Completa el proyecto y lanza la revision solo para proyectos Serviflow.

        Se ejecuta cuando cambia el estado real de una tarea de proyecto.
        Solo actua sobre proyectos que tengan una solicitud Serviflow de tipo
        presupuesto vinculada.
        """
        for project in self:
            serviflow_task = self.env['serviflow.task'].sudo().search([
                ('project_id', '=', project.id),
                ('task_type', '=', 'budget'),
            ], order='create_date desc', limit=1)

            # No tocar proyectos ajenos a Serviflow.
            if not serviflow_task:
                continue

            project_tasks = self.env['project.task'].sudo().search([
                ('project_id', '=', project.id),
            ])

            if not project_tasks:
                continue

            # El estado tecnico "Hecho" de project.task en Odoo 17 es 1_done.
            if any(project_task.state != '1_done' for project_task in project_tasks):
                continue

            complete_status = self.env['project.status'].sudo().search([
                ('name', '=', 'Completo'),
            ], limit=1)

            if not complete_status:
                raise UserError(
                    _("No se encontro el estado de proyecto 'Completo'.")
                )

            # Si ya estaba Completo, esta finalizacion ya fue procesada.
            # Tras un rechazo Serviflow lo devuelve a "En proceso", por lo que
            # al completar de nuevo se generara correctamente una nueva ronda.
            if project.project_status == complete_status:
                continue

            # Debe existir un presupuesto antes de poder enviarlo a revision.
            serviflow_task._ensure_sale_order()
            if not serviflow_task.sale_order_id:
                raise UserError(
                    _(
                        'No hay ningun presupuesto vinculado a esta solicitud. '
                        'Crea o vincula el presupuesto antes de completar el proyecto.'
                    )
                )

            project.sudo().write({
                'project_status': complete_status.id,
            })

            serviflow_task.sudo().write({
                'state': 'done',
                'completed_at': fields.Datetime.now(),
            })
            serviflow_task._close_user_activities()
            serviflow_task._create_review_tasks()

            project.message_post(
                body=(
                    '<b>Trabajo tecnico completado.</b><br/>'
                    'Todas las tareas del proyecto estan hechas. '
                    'El presupuesto se ha enviado a revision interna.'
                )
            )
