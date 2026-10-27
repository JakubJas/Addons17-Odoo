
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ServiflowOfiproBatch(models.Model):
    _name = 'serviflow.ofipro.batch'
    _description = 'Lote de importacion historica OfiPro'
    _order = 'id desc'

    name = fields.Char(
        required=True,
        default='Nuevo lote',
        copy=False,
    )

    filename = fields.Char(readonly=True)

    user_id = fields.Many2one(
        'res.users',
        default=lambda self: self.env.user,
        readonly=True,
    )

    state = fields.Selection(
        [
            ('active', 'Activo'),
            ('partial', 'Reversion parcial'),
            ('reverted', 'Revertido'),
        ],
        default='active',
        readonly=True,
    )

    project_ids = fields.One2many(
        'project.project',
        'ofipro_batch_id',
        string='Proyectos del lote',
    )

    imported_total = fields.Integer(readonly=True)
    removed_total = fields.Integer(readonly=True)
    rollback_log = fields.Text(readonly=True)

    project_count = fields.Integer(
        compute='_compute_project_count',
    )

    @api.depends('project_ids')
    def _compute_project_count(self):
        for batch in self:
            batch.project_count = len(batch.project_ids)

    def action_open_projects(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Proyectos del lote',
            'res_model': 'project.project',
            'view_mode': 'tree,form',
            'domain': [
                ('ofipro_batch_id', '=', self.id)
            ],
            'target': 'current',
        }

    def action_rollback(self):
        self.ensure_one()

        if not self.env.user.has_group(
            'sb_hr_serviflow.group_serviflow_manager'
        ):
            raise UserError(
                _('No tienes permisos para revertir importaciones OfiPro.')
            )

        self.env.cr.execute(
            'SELECT pg_advisory_xact_lock(%s)',
            (81736251,),
        )

        projects = self.env[
            'project.project'
        ].sudo().search([
            ('ofipro_batch_id', '=', self.id)
        ])

        deleted = 0
        blocked = []

        for project in projects:
            reasons = []

            if self.env[
                'project.task'
            ].sudo().search_count([
                ('project_id', '=', project.id)
            ]):
                reasons.append('tareas asociadas')

            if (
                'account.analytic.line'
                in self.env.registry.models
                and 'project_id'
                in self.env['account.analytic.line']._fields
            ):
                if self.env[
                    'account.analytic.line'
                ].sudo().search_count([
                    ('project_id', '=', project.id)
                ]):
                    reasons.append('partes de horas')

            if 'serviflow.task' in self.env.registry.models:
                if self.env[
                    'serviflow.task'
                ].sudo().search_count([
                    ('project_id', '=', project.id)
                ]):
                    reasons.append('flujo Serviflow')

            if project.serviflow_sale_order_ids:
                reasons.append('presupuestos asociados')

            if project.serviflow_opportunity_id:
                reasons.append('oportunidad CRM asociada')

            if reasons:
                blocked.append(
                    '%s [%s]: %s'
                    % (
                        project.name,
                        project.id,
                        ', '.join(reasons),
                    )
                )
                continue

            try:
                with self.env.cr.savepoint():
                    project.sudo().unlink()

                deleted += 1

            except Exception as exc:
                blocked.append(
                    '%s [%s]: error al borrar: %s'
                    % (
                        project.name,
                        project.id,
                        str(exc)[:180],
                    )
                )

        remaining = self.env[
            'project.project'
        ].sudo().search_count([
            ('ofipro_batch_id', '=', self.id)
        ])

        self.write({
            'removed_total': self.removed_total + deleted,
            'state': (
                'reverted'
                if not remaining
                else 'partial'
            ),
            'rollback_log': (
                'Eliminados en esta operacion: %s\n'
                'Restantes: %s\n\n%s'
            ) % (
                deleted,
                remaining,
                '\n'.join(blocked)
                if blocked
                else 'Sin bloqueos.',
            ),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Lote OfiPro',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
