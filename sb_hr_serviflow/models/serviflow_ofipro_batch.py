
from odoo import api, fields, models, _
from odoo.exceptions import UserError


ROLLBACK_BATCH_SIZE = 50


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

    rollback_last_id = fields.Integer(
        string='Ultimo proyecto revisado',
        readonly=True,
        default=0,
        copy=False,
    )

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
                ('ofipro_batch_id', '=', self.id),
            ],
            'target': 'current',
        }

    def _rollback_block_reasons(self, project):
        reasons = []

        if self.env['project.task'].sudo().search_count([
            ('project_id', '=', project.id),
        ]):
            reasons.append('tareas asociadas')

        if (
            'account.analytic.line'
            in self.env.registry.models
            and 'project_id'
            in self.env['account.analytic.line']._fields
        ):
            if self.env['account.analytic.line'].sudo().search_count([
                ('project_id', '=', project.id),
            ]):
                reasons.append('partes de horas')

        if 'serviflow.task' in self.env.registry.models:
            if self.env['serviflow.task'].sudo().search_count([
                ('project_id', '=', project.id),
            ]):
                reasons.append('flujo Serviflow')

        if project.serviflow_sale_order_ids:
            reasons.append('presupuestos asociados')

        if project.serviflow_opportunity_id:
            reasons.append('oportunidad CRM asociada')

        return reasons

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

        self.invalidate_recordset()

        if self.state == 'reverted':
            raise UserError(
                _('Este lote ya esta completamente revertido.')
            )

        project_model = self.env['project.project'].sudo()

        domain = [
            ('ofipro_batch_id', '=', self.id),
        ]

        remaining_before = project_model.search_count(domain)

        if not remaining_before:
            self.write({
                'state': 'reverted',
                'rollback_log': 'No quedan proyectos por eliminar.',
            })
            return self._open_batch()

        # Continuamos desde el ultimo proyecto revisado.
        # Los bloqueados no impiden avanzar.
        projects = project_model.search(
            domain + [
                ('id', '>', self.rollback_last_id),
            ],
            order='id asc',
            limit=ROLLBACK_BATCH_SIZE,
        )

        if not projects:
            self.write({
                'state': 'partial',
                'rollback_log': (
                    'Se han revisado todos los proyectos del lote.\n'
                    'Quedan %s proyectos bloqueados o no eliminados.\n'
                    'No se volveran a intentar automaticamente.'
                ) % remaining_before,
            })
            return self._open_batch()

        deleted = 0
        blocked = []
        last_id = self.rollback_last_id

        for project in projects:
            last_id = project.id

            reasons = self._rollback_block_reasons(project)

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
                    project.unlink()
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

        remaining = project_model.search_count(domain)

        more_to_review = project_model.search_count(
            domain + [
                ('id', '>', last_id),
            ]
        )

        previous_log = self.rollback_log or ''

        new_log = (
            'Bloque revisado hasta proyecto ID %s\n'
            'Revisados en esta operacion: %s\n'
            'Eliminados en esta operacion: %s\n'
            'Proyectos restantes: %s\n'
            'Pendientes de revisar: %s\n\n'
            % (
                last_id,
                len(projects),
                deleted,
                remaining,
                more_to_review,
            )
        )

        if blocked:
            new_log += (
                'Bloqueados o con errores:\n'
                + '\n'.join(blocked)
                + '\n\n'
            )

        if not more_to_review and remaining:
            new_log += (
                'REVISION FINALIZADA: quedan proyectos '
                'que requieren revision manual.\n\n'
            )

        # Limitar el historial para no crear un campo
        # de texto excesivamente grande.
        combined_log = (
            new_log + previous_log
        )[:60000]

        self.write({
            'rollback_last_id': last_id,
            'removed_total': self.removed_total + deleted,
            'state': (
                'reverted' if not remaining else 'partial'
            ),
            'rollback_log': combined_log,
        })

        return self._open_batch()

    def _open_batch(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Lote OfiPro',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
