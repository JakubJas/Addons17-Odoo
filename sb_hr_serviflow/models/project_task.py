from odoo import models


class ProjectTask(models.Model):
    _inherit = 'project.task'

    def write(self, vals):
        result = super().write(vals)

        # El flujo Serviflow se dispara por el estado real de la tarea,
        # no por la columna/etapa visual del kanban.
        if 'state' not in vals:
            return result

        for project in self.mapped('project_id'):
            if project:
                project._serviflow_check_tasks_completion()

        return result
