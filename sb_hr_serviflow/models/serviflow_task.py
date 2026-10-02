from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ServiflowTask(models.Model):
    _name = 'serviflow.task'
    _description = 'Solicitud Serviflow'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Nombre', required=True, tracking=True)

    opportunity_id = fields.Many2one(
        'crm.lead',
        string='Oportunidad',
        required=True,
        tracking=True,
    )

    state = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('accepted', 'Aceptada'),
            ('done', 'Hecha'),
            ('cancelled', 'Cancelada'),
        ],
        string='Estado',
        default='pending',
        required=True,
        tracking=True,
    )

    assigned_user_id = fields.Many2one(
        'res.users',
        string='Usuario asignado',
        tracking=True,
    )

    accepted_user_id = fields.Many2one(
        'res.users',
        string='Aceptada por',
        tracking=True,
    )

    note = fields.Text(string='Notas')

    reassign_user_id = fields.Many2one(
        'res.users',
        string='Reasignar a',
        domain=lambda self: [
            (
                'groups_id',
                'in',
                [self.env.ref('sb_hr_serviflow.group_serviflow_office_tech').id],
            )
        ],
    )

    task_type = fields.Selection(
        [
            ('budget', 'Presupuesto tecnico'),
            ('review', 'Revision'),
        ],
        string='Tipo de solicitud',
        default='budget',
        required=True,
        tracking=True,
    )

    review_result = fields.Selection(
        [
            ('pending', 'Pendiente'),
            ('approved', 'Aprobado'),
            ('rejected', 'Rechazado'),
        ],
        string='Resultado revision',
        default='pending',
        tracking=True,
    )

    review_round = fields.Integer(
        string='Ronda de revision',
        default=1,
        tracking=True,
    )

    sale_order_id = fields.Many2one(
        'sale.order',
        string='Presupuesto',
        tracking=True,
        domain="[('opportunity_id', '=', opportunity_id)]",
    )
    
    sale_order_ids = fields.Many2many(
        "sale.order",
        string="Presupuestos del proyecto",
        related="project_id.serviflow_sale_order_ids",
        readonly=True,
    )

    requested_by_user_id = fields.Many2one(
        'res.users',
        string='Solicitado por',
        tracking=True,
    )

    requested_at = fields.Datetime(string='Fecha de solicitud', tracking=True)
    accepted_at = fields.Datetime(string='Fecha de aceptacion', tracking=True)
    completed_at = fields.Datetime(string='Fecha PPTO terminado', tracking=True)
    reviewed_at = fields.Datetime(string='Fecha de revision', tracking=True)
    final_approved_at = fields.Datetime(string='Fecha aprobacion final', tracking=True)
    rejection_reason = fields.Text(string='Motivo de rechazo', tracking=True)

    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        tracking=True,
    )

    project_task_id = fields.Many2one(
        'project.task',
        string='Tarea de proyecto',
        tracking=True,
    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _ensure_sale_order(self):

        for task in self:

            if (
                task.project_id
                and task.project_id.serviflow_sale_order_ids
            ):

                quotations = (
                    task.project_id.serviflow_sale_order_ids
                )

                # Mantener el campo antiguo sincronizado
                if (
                    not task.sale_order_id
                    or task.sale_order_id not in quotations
                ):
                    task.sudo().write({
                        "sale_order_id": quotations[0].id,
                    })

                continue

            if task.sale_order_id:

                if task.project_id:
                    task.project_id.sudo().write({
                        "serviflow_sale_order_ids": [
                            (4, task.sale_order_id.id)
                        ],
                    })

                continue

            if not task.opportunity_id:
                continue

            quotations = self.env[
                "sale.order"
            ].sudo().search([
                (
                    "opportunity_id",
                    "=",
                    task.opportunity_id.id,
                ),
            ])

            if not quotations:
                continue

            # Si tenemos proyecto, recuperar todos
            if task.project_id:
                task.project_id.sudo().write({
                    "serviflow_sale_order_ids": [
                        (6, 0, quotations.ids)
                    ],
                })

            # Compatibilidad antigua
            task.sudo().write({
                "sale_order_id": quotations[0].id,
            })

        return True

    def _review_scope_domain(self):
        """Dominio comun para aislar revisiones por proyecto.

        Evita mezclar rondas si una misma oportunidad genera mas de un proyecto
        a lo largo del tiempo.
        """
        self.ensure_one()

        domain = [('task_type', '=', 'review')]
        if self.project_id:
            domain.append(('project_id', '=', self.project_id.id))
        else:
            domain.append(('opportunity_id', '=', self.opportunity_id.id))
        return domain

    # -------------------------------------------------------------------------
    # Solicitud tecnica / asignacion
    # -------------------------------------------------------------------------

    def action_accept(self):
        self.ensure_one()

        if self.task_type != 'budget':
            raise UserError(_('Solo se pueden aceptar solicitudes de presupuesto tecnico.'))

        if self.state != 'pending':
            raise UserError(_('Esta solicitud ya ha sido aceptada por otro usuario.'))

        if not self.project_id:
            raise UserError(_('La solicitud no tiene un proyecto asociado.'))

        if not self.project_task_id:
            raise UserError(_('La solicitud no tiene una tarea de proyecto asociada.'))

        self.write({
            'state': 'accepted',
            'accepted_user_id': self.env.user.id,
            'assigned_user_id': self.env.user.id,
            'accepted_at': fields.Datetime.now(),
        })

        # El trabajo real vive en project.task.
        self.project_task_id.sudo().write({
            'user_ids': [(6, 0, [self.env.user.id])],
            'state': '01_in_progress',
        })

        # Mantener la oportunidad asignada al tecnico que acepta.
        self.opportunity_id.sudo().write({
            'user_id': self.env.user.id,
        })

        self._close_user_activities()

        self.message_post(
            body=f'Solicitud aceptada por <b>{self.env.user.name}</b>.'
        )
        self.project_task_id.message_post(
            body=(
                f'Tarea aceptada y asignada a <b>{self.env.user.name}</b> '
                'mediante Serviflow.'
            )
        )

        return {
            'type': 'ir.actions.act_window',
            'name': self.project_task_id.name,
            'res_model': 'project.task',
            'res_id': self.project_task_id.id,
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'current',
        }

    def action_done(self):
        """Compatibilidad: el tecnico ya no finaliza desde Serviflow."""
        raise UserError(
            _(
                'El trabajo tecnico se finaliza desde la tarea del proyecto. '
                'Marca la tarea como Hecho en Proyecto.'
            )
        )

    def action_cancel(self):
        for task in self:
            task.write({'state': 'cancelled'})
        return True

    # -------------------------------------------------------------------------
    # Reasignacion
    # -------------------------------------------------------------------------

    def action_reassign_to_me(self):
        for task in self:
            if task.task_type != 'budget':
                raise UserError(_('No se pueden reasignar tareas de revision.'))

            if task.state not in ('pending', 'accepted'):
                raise UserError(
                    _('Solo se pueden reasignar solicitudes pendientes o aceptadas.')
                )

            task.write({
                'state': 'accepted',
                'assigned_user_id': self.env.user.id,
                'accepted_user_id': self.env.user.id,
                'accepted_at': fields.Datetime.now(),
            })

            if task.project_task_id:
                task.project_task_id.sudo().write({
                    'user_ids': [(6, 0, [self.env.user.id])],
                    'state': '01_in_progress',
                })

            task.opportunity_id.sudo().write({'user_id': self.env.user.id})
            task._close_user_activities()

        return True

    def action_reassign(self):
        for task in self:
            if task.task_type != 'budget':
                raise UserError(
                    _(
                        'No se pueden reasignar tareas de revision. '
                        'Cambia el revisor desde la configuracion de Revisores.'
                    )
                )

            if not task.reassign_user_id:
                raise UserError(_('Selecciona un usuario para reasignar.'))

            new_user = task.reassign_user_id

            task.write({
                'state': 'accepted',
                'assigned_user_id': new_user.id,
                'accepted_user_id': new_user.id,
                'accepted_at': fields.Datetime.now(),
            })

            if task.project_task_id:
                task.project_task_id.sudo().write({
                    'user_ids': [(6, 0, [new_user.id])],
                    'state': '01_in_progress',
                })

            task.opportunity_id.sudo().write({'user_id': new_user.id})

            task._close_user_activities()
            task._create_user_activity()

            task.message_post(
                body=(
                    f'Solicitud reasignada a {new_user.name} '
                    f'por {self.env.user.name}'
                )
            )
            task.reassign_user_id = False

        return True

    # -------------------------------------------------------------------------
    # Presupuesto
    # -------------------------------------------------------------------------

    def action_create_quotation(self):
        """Metodo conservado para reutilizarlo desde Project en el siguiente paso."""
        self.ensure_one()

        if self.task_type != 'budget':
            raise UserError(
                _('Solo se puede crear un presupuesto desde una solicitud tecnica.')
            )

        self._ensure_sale_order()

        if self.sale_order_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'sale.order',
                'res_id': self.sale_order_id.id,
                'views': [[False, 'form']],
                'view_mode': 'form',
                'target': 'current',
            }

        lead = self.opportunity_id
        if not lead.partner_id:
            raise UserError(
                _('La oportunidad debe tener un cliente antes de crear el presupuesto.')
            )

        quotation = self.env['sale.order'].sudo().create({
            'partner_id': lead.partner_id.id,
            'opportunity_id': lead.id,
            'origin': lead.name,
        })

        self.write({'sale_order_id': quotation.id})
        self.message_post(
            body=f'Presupuesto {quotation.name} creado y vinculado a la solicitud.'
        )

        return {
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order',
            'res_id': quotation.id,
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'current',
        }

    # -------------------------------------------------------------------------
    # Revisiones
    # -------------------------------------------------------------------------

    def _create_review_tasks(self):
        for task in self:

            if task.task_type != 'budget':
                continue

            task._ensure_sale_order()

            if not task.sale_order_id:
                raise UserError(
                    _('No se encontro ningun presupuesto vinculado a esta solicitud.')
                )

            review_domain = task._review_scope_domain()

            # =====================================================
            # Calcular siguiente ronda
            # =====================================================

            last_review = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", task.project_id.id),
                ("task_type", "=", "review"),
            ], order="review_round desc", limit=1)

            new_round = (
                last_review.review_round + 1
                if last_review
                else 1
            )

            # =====================================================
            # Evitar más de una ronda abierta
            # =====================================================

            current_open_reviews = self.env[
                'serviflow.task'
            ].sudo().search_count(
                review_domain + [
                    ('review_result', '=', 'pending'),
                    ('state', '=', 'pending'),
                ]
            )

            if current_open_reviews:
                continue

            # =====================================================
            # Obtener revisores
            # =====================================================

            reviewers = self.env[
                'serviflow.reviewer.config'
            ].sudo().search([
                ('active', '=', True),
            ])

            if not reviewers:
                raise UserError(
                    _('No hay revisores configurados en Serviflow.')
                )

            # =====================================================
            # Crear revisiones
            # =====================================================

            for reviewer in reviewers:

                review_task = self.env[
                    'serviflow.task'
                ].sudo().create({

                    'name': (
                        f'{reviewer.name} - '
                        f'{task.opportunity_id.name}'
                    ),

                    'opportunity_id': task.opportunity_id.id,

                    # Campo antiguo para compatibilidad
                    'sale_order_id': task.sale_order_id.id,

                    # Proyecto y tarea real
                    'project_id': (
                        task.project_id.id
                        if task.project_id
                        else False
                    ),

                    'project_task_id': (
                        task.project_task_id.id
                        if task.project_task_id
                        else False
                    ),

                    'task_type': 'review',

                    'review_round': new_round,

                    'assigned_user_id': reviewer.user_id.id,
                    'accepted_user_id': False,

                    'state': 'pending',
                    'review_result': 'pending',

                    'note': (
                        f'Revision asignada a '
                        f'{reviewer.name}.'
                    ),
                })

                review_task._create_user_activity()

    def action_review_approve(self):
        for task in self:
            if task.task_type != "review":
                raise UserError(
                    _("Esta solicitud no es una revisión.")
                )

            if task.assigned_user_id != self.env.user:
                raise UserError(
                    _("Solo el revisor asignado puede aprobar esta revisión.")
                )

            if task.review_result != "pending":
                raise UserError(
                    _("Esta revisión ya ha sido procesada.")
                )

            task.write({
                "review_result": "approved",
                "state": "done",
                "accepted_user_id": self.env.user.id,
                "reviewed_at": fields.Datetime.now(),
            })

            task._close_user_activities()

            task.message_post(
                body=(
                    f"Revisión aprobada por "
                    f"<b>{self.env.user.name}</b>."
                )
            )

            task._check_all_reviews_done()

        return True

    def _check_all_reviews_done(self):
        for current_review in self:

            if current_review.task_type != "review":
                continue

            project = current_review.project_id

            if not project:
                continue

            current_round = current_review.review_round

            reviews = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", project.id),
                ("task_type", "=", "review"),
                ("review_round", "=", current_round),
            ])

            if not reviews:
                continue

            # =====================================================
            # Si hay algún rechazo -> no aprobar
            # =====================================================

            if any(
                review.review_result == "rejected"
                for review in reviews
            ):
                continue

            # =====================================================
            # Si queda alguna pendiente -> esperar
            # =====================================================

            if any(
                review.review_result == "pending"
                for review in reviews
            ):
                continue

            # =====================================================
            # Todas tienen que estar aprobadas
            # =====================================================

            if not all(
                review.review_result == "approved"
                for review in reviews
            ):
                continue

            now = fields.Datetime.now()

            reviews.sudo().write({
                "final_approved_at": now,
            })

            # =====================================================
            # CRM -> PRESUPUESTADO
            # =====================================================

            opportunity = current_review.opportunity_id

            if opportunity:
                budgeted_stage = self.env["crm.stage"].sudo().search([
                    ("name", "=", "Presupuestado"),
                ], limit=1)

                if not budgeted_stage:
                    raise UserError(
                        _(
                            "No se encontró la etapa CRM "
                            "'Presupuestado'."
                        )
                    )

                opportunity.with_context(
                    serviflow_from_wizard=True
                ).sudo().write({
                    "stage_id": budgeted_stage.id,
                })

                opportunity.message_post(
                    body=(
                        "<b>Presupuesto aprobado internamente.</b><br/>"
                        f"Todos los revisores han aprobado "
                        f"la ronda {current_round}."
                    )
                )

            # =====================================================
            # PROJECT permanece COMPLETO
            # =====================================================

            complete_status = self.env[
                "project.status"
            ].sudo().search([
                ("name", "=", "Completo"),
            ], limit=1)

            if complete_status:
                if project.project_status != complete_status:
                    project.sudo().write({
                        "project_status": complete_status.id,
                    })

            project.message_post(
                body=(
                    "<b>Presupuesto aprobado internamente.</b><br/>"
                    f"Ronda de revisión: {current_round}.<br/>"
                    "Todos los verificadores han aprobado."
                )
            )

        return True

    def _send_back_to_technical(self, rejection_reason=False):
        for review in self:

            if review.task_type != "review":
                continue

            opportunity = review.opportunity_id
            project = review.project_id
            project_task = review.project_task_id

            if not project:
                raise UserError(
                    _("La revisión no tiene un proyecto asociado.")
                )

            if not project_task:
                raise UserError(
                    _("La revisión no tiene una tarea de proyecto asociada.")
                )

            # =====================================================
            # 1. CRM -> mantener Solicitud PPTO Técnico
            # =====================================================

            technical_stage = self.env["crm.stage"].sudo().search([
                ("name", "=", "Solicitado Presupuesto Técnico")
            ], limit=1)

            if technical_stage and opportunity:
                if opportunity.stage_id != technical_stage:
                    opportunity.with_context(
                        serviflow_from_wizard=True
                    ).sudo().write({
                        "stage_id": technical_stage.id,
                    })

            # =====================================================
            # 2. Proyecto -> EN PROGRESO
            # =====================================================

            progress_status = self.env["project.status"].sudo().search([
                ("name", "=", "En progreso"),
            ], limit=1)

            if not progress_status:
                raise UserError(
                    _(
                        "No se encontró el estado de proyecto "
                        "'En progreso'."
                    )
                )

            if project.project_status != progress_status:
                project.sudo().write({
                    "project_status": progress_status.id,
                })

            # =====================================================
            # 3. Tarea -> EN PROCESO
            # =====================================================
            #
            # IMPORTANTE:
            # Primero cambiamos el proyecto a En progreso.
            #
            # Así, cuando el write() de project.task ejecute
            # _serviflow_check_tasks_completion(), no volverá
            # a lanzar una revisión accidentalmente.
            # =====================================================

            if project_task.state != "01_in_progress":
                project_task.sudo().write({
                    "state": "01_in_progress",
                })

            # =====================================================
            # 4. Cancelar las demás revisiones de esta ronda
            # =====================================================

            other_reviews = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", project.id),
                ("task_type", "=", "review"),
                ("review_round", "=", review.review_round),
                ("id", "!=", review.id),
                ("state", "in", ["pending", "accepted"]),
            ])

            for other_review in other_reviews:
                other_review._close_user_activities()

            if other_reviews:
                other_reviews.write({
                    "state": "cancelled",
                })

            # =====================================================
            # 5. Buscar solicitud técnica principal
            # =====================================================

            budget_task = self.env["serviflow.task"].sudo().search([
                ("project_id", "=", project.id),
                ("task_type", "=", "budget"),
            ], order="create_date desc", limit=1)

            # =====================================================
            # 6. Recuperar técnico responsable
            # =====================================================

            technical_user = False

            # Preferimos el asignado real en Project
            if project_task.user_ids:
                technical_user = project_task.user_ids[0]

            # Compatibilidad con Serviflow
            elif budget_task:
                technical_user = (
                    budget_task.accepted_user_id
                    or budget_task.assigned_user_id
                )

            # =====================================================
            # 7. Reactivar solicitud interna Serviflow
            # =====================================================

            if budget_task:
                values = {
                    "state": "accepted",
                }

                if technical_user:
                    values.update({
                        "assigned_user_id": technical_user.id,
                        "accepted_user_id": technical_user.id,
                    })

                budget_task.sudo().write(values)

            # =====================================================
            # 8. Chatter de la tarea Project
            # =====================================================

            reason_html = rejection_reason or "Sin motivo indicado."

            project_task.message_post(
                body=(
                    "<b>Presupuesto devuelto para corrección.</b><br/>"
                    f"<b>Revisor:</b> {self.env.user.name}<br/>"
                    f"<b>Ronda:</b> {review.review_round}<br/><br/>"
                    f"<b>Motivo del rechazo:</b><br/>"
                    f"{reason_html}"
                )
            )

            # =====================================================
            # 9. Chatter del proyecto
            # =====================================================

            project.message_post(
                body=(
                    "<b>Proyecto devuelto a En progreso.</b><br/>"
                    f"El presupuesto ha sido rechazado por "
                    f"{self.env.user.name}.<br/><br/>"
                    f"<b>Motivo:</b><br/>"
                    f"{reason_html}"
                )
            )

            # =====================================================
            # 10. Crear actividad al técnico
            # =====================================================

            if technical_user:
                activity_type = self.env.ref(
                    "mail.mail_activity_data_todo",
                    raise_if_not_found=False,
                )

                if activity_type:
                    project_task.activity_schedule(
                        activity_type_id=activity_type.id,
                        user_id=technical_user.id,
                        summary="Corregir presupuesto técnico",
                        note=(
                            f"<b>Presupuesto rechazado.</b><br/>"
                            f"<b>Revisor:</b> {self.env.user.name}<br/>"
                            f"<b>Ronda:</b> {review.review_round}<br/><br/>"
                            f"<b>Motivo:</b><br/>"
                            f"{reason_html}"
                        ),
                    )

            # =====================================================
            # 11. Trazabilidad interna Serviflow
            # =====================================================

            if budget_task:
                budget_task.message_post(
                    body=(
                        f"Presupuesto devuelto para corrección por "
                        f"<b>{self.env.user.name}</b>.<br/>"
                        f"<b>Motivo:</b><br/>{reason_html}"
                    )
                )

        return True

    # -------------------------------------------------------------------------
    # Actividades
    # -------------------------------------------------------------------------

    def _create_user_activity(self):
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo',
            raise_if_not_found=False,
        )
        model_id = self.env['ir.model']._get_id('serviflow.task')

        for task in self:
            if not activity_type or not task.assigned_user_id:
                continue

            existing = self.env['mail.activity'].sudo().search_count([
                ('res_model', '=', 'serviflow.task'),
                ('res_id', '=', task.id),
                ('user_id', '=', task.assigned_user_id.id),
            ])
            if existing:
                continue

            self.env['mail.activity'].sudo().create({
                'res_model_id': model_id,
                'res_id': task.id,
                'user_id': task.assigned_user_id.id,
                'activity_type_id': activity_type.id,
                'summary': task._get_activity_summary(),
                'note': task.note or '',
                'date_deadline': fields.Date.today(),
            })

    def _create_group_activities(self):
        activity_type = self.env.ref(
            'mail.mail_activity_data_todo',
            raise_if_not_found=False,
        )
        group = self.env.ref(
            'sb_hr_serviflow.group_serviflow_office_tech',
            raise_if_not_found=False,
        )
        model_id = self.env['ir.model']._get_id('serviflow.task')

        for task in self:
            if not activity_type or not group:
                continue

            for user in group.users:
                existing = self.env['mail.activity'].sudo().search_count([
                    ('res_model', '=', 'serviflow.task'),
                    ('res_id', '=', task.id),
                    ('user_id', '=', user.id),
                ])
                if existing:
                    continue

                self.env['mail.activity'].sudo().create({
                    'res_model_id': model_id,
                    'res_id': task.id,
                    'user_id': user.id,
                    'activity_type_id': activity_type.id,
                    'summary': task._get_activity_summary(),
                    'note': task.note or '',
                    'date_deadline': fields.Date.today(),
                })

    def _close_user_activities(self):
        for task in self:
            activities = self.env['mail.activity'].sudo().search([
                ('res_model', '=', 'serviflow.task'),
                ('res_id', '=', task.id),
            ])
            if activities:
                activities.action_feedback(feedback='Gestionado desde Serviflow')

    def _get_activity_summary(self):
        self.ensure_one()

        if self.task_type == 'budget' and self.state == 'pending':
            return f'PPTO tecnico: {self.opportunity_id.name}'

        if self.task_type == 'budget' and self.state == 'accepted':
            return f'Correccion/Trabajo PPTO: {self.opportunity_id.name}'

        if self.task_type == 'review':
            return f'Revision presupuesto: {self.opportunity_id.name}'

        return self.name

    # -------------------------------------------------------------------------
    # Systray
    # -------------------------------------------------------------------------

    @api.model
    def get_my_pending_systray_tasks(self):
        activities = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'serviflow.task'),
            ('user_id', '=', self.env.user.id),
        ])
        task_ids = activities.mapped('res_id')

        tasks = self.sudo().search([
            ('id', 'in', task_ids),
            ('task_type', '=', 'budget'),
            ('state', '=', 'pending'),
        ])

        return [
            {
                'id': task.id,
                'name': task.name,
                'opportunity': task.opportunity_id.name or '',
            }
            for task in tasks
        ]

    @api.model
    def get_my_pending_systray_reviews(self):
        activities = self.env['mail.activity'].sudo().search([
            ('res_model', '=', 'serviflow.task'),
            ('user_id', '=', self.env.user.id),
        ])
        task_ids = activities.mapped('res_id')

        reviews = self.sudo().search([
            ('id', 'in', task_ids),
            ('task_type', '=', 'review'),
            ('assigned_user_id', '=', self.env.user.id),
            ('review_result', '=', 'pending'),
            ('state', '=', 'pending'),
        ])

        reviews._ensure_sale_order()

        return [
            {
                'id': review.id,
                'name': review.name,
                'opportunity': review.opportunity_id.name or '',
                'round': review.review_round,
            }
            for review in reviews
        ]

    # -------------------------------------------------------------------------
    # Rechazo con motivo
    # -------------------------------------------------------------------------

    def action_open_reject_wizard(self):
        self.ensure_one()

        if self.task_type != 'review':
            raise UserError(_('Esta tarea no es una revision.'))

        if self.assigned_user_id != self.env.user:
            raise UserError(
                _('Solo el revisor asignado puede rechazar esta revision.')
            )

        if self.review_result != 'pending':
            raise UserError(_('Esta revision ya fue procesada.'))

        return {
            'type': 'ir.actions.act_window',
            'name': 'Rechazar revision',
            'res_model': 'serviflow.reject.wizard',
            'views': [[False, 'form']],
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_task_id': self.id},
        }

    def action_open_project_quotations(self):
        self.ensure_one()

        quotations = self.sale_order_ids

        if not quotations:
            raise UserError(
                _("Este proyecto no tiene presupuestos asociados.")
            )

        # Solo uno: abrir directamente
        if len(quotations) == 1:
            quotation = quotations[0]

            return {
                "type": "ir.actions.act_window",
                "name": quotation.name,
                "res_model": "sale.order",
                "res_id": quotation.id,
                "views": [[False, "form"]],
                "view_mode": "form",
                "target": "current",
            }

        # Varios: mostrar listado
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