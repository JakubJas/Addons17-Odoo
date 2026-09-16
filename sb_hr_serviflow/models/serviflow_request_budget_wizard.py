from odoo import fields, models, _
from odoo.exceptions import UserError


class ServiflowRequestBudgetWizard(models.TransientModel):
    _name = 'serviflow.request.budget.wizard'
    _description = 'Solicitar Presupuesto Tecnico'

    opportunity_id = fields.Many2one(
        'crm.lead',
        string='Oportunidad',
        required=True,
        readonly=True,
    )

    technical_notes = fields.Text(
        string='Indicaciones para Oficina Tecnica',
        required=True,
    )

    priority = fields.Selection(
        [
            ('0', 'Normal'),
            ('1', 'Baja'),
            ('2', 'Alta'),
            ('3', 'Muy alta'),
        ],
        string='Prioridad',
        default='0',
        required=True,
    )

    requested_date = fields.Date(
        string='Fecha deseada',
    )

    def action_confirm(self):
        self.ensure_one()

        if not self.technical_notes or not self.technical_notes.strip():
            raise UserError(
                _('Debes indicar las instrucciones para Oficina Tecnica.')
            )

        lead = self.opportunity_id

        crm_stage = self.env['crm.stage'].search([
            ('name', '=', 'Solicitado Presupuesto Tecnico')
        ], limit=1)

        if not crm_stage:
            # Compatibilidad con el nombre con tilde usado actualmente.
            crm_stage = self.env['crm.stage'].search([
                ('name', '=', 'Solicitado Presupuesto Técnico')
            ], limit=1)

        if not crm_stage:
            raise UserError(
                _("No se encontro la etapa 'Solicitado Presupuesto Tecnico'.")
            )

        priority_labels = {
            '0': 'Normal',
            '1': 'Baja',
            '2': 'Alta',
            '3': 'Muy alta',
        }
        priority_name = priority_labels.get(self.priority, 'Normal')

        requested_date_text = (
            self.requested_date.strftime('%d/%m/%Y')
            if self.requested_date
            else 'Sin fecha indicada'
        )

        serviflow_note = (
            f'PRIORIDAD: {priority_name}\n'
            f'FECHA DESEADA: {requested_date_text}\n\n'
            f'INDICACIONES:\n{self.technical_notes.strip()}'
        )

        existing = self.env['serviflow.task'].search([
            ('opportunity_id', '=', lead.id),
            ('task_type', '=', 'budget'),
            ('state', 'in', ['pending', 'accepted']),
        ], limit=1)

        if existing:
            raise UserError(
                _('Ya existe una solicitud de presupuesto tecnico activa para esta oportunidad.')
            )

        pending_status = self.env['project.status'].sudo().search([
            ('name', '=', 'Pendiente'),
        ], limit=1)

        if not pending_status:
            raise UserError(
                _("No se encontro el estado de proyecto 'Pendiente'.")
            )

        # Proyecto deliberadamente minimo: nombre, estado y sin gerente.
        project = self.env['project.project'].sudo().create({
            'name': lead.name,
            'project_status': pending_status.id,
            'user_id': False,
        })

        # Tarea inicial deliberadamente minima. Se asigna cuando un tecnico acepta.
        project_task = self.env['project.task'].sudo().create({
            'name': 'Preparar presupuesto tecnico',
            'project_id': project.id,
        })

        serviflow_task = self.env['serviflow.task'].sudo().create({
            'name': f'PPTO - {lead.name}',
            'opportunity_id': lead.id,
            'task_type': 'budget',
            'state': 'pending',
            'note': serviflow_note,
            'project_id': project.id,
            'project_task_id': project_task.id,
            'requested_by_user_id': self.env.user.id,
            'requested_at': fields.Datetime.now(),
        })

        serviflow_task._create_group_activities()

        lead.with_context(serviflow_from_wizard=True).write({
            'stage_id': crm_stage.id,
        })

        lead.message_post(
            body=(
                '<b>Solicitud de presupuesto tecnico creada</b><br/>'
                f'<b>Prioridad:</b> {priority_name}<br/>'
                f'<b>Fecha deseada:</b> {requested_date_text}<br/>'
                f'<b>Indicaciones:</b> {self.technical_notes}'
            )
        )

        return {'type': 'ir.actions.act_window_close'}
