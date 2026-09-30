from odoo import models, fields, api
from odoo.exceptions import UserError
from datetime import timedelta


class HrOvertimeEntry(models.Model):
    _name = "hr.overtime.entry"
    _description = "Overtime Bank Entry"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    MIN_HOURS = -80
    MAX_HOURS = 80

    # =========================================================
    # CAMPOS PRINCIPALES
    # =========================================================

    employee_id = fields.Many2one(
        "hr.employee",
        required=True,
    )

    date = fields.Date(
        default=fields.Date.today,
        tracking=True,
    )

    hours = fields.Float(
        tracking=True,
    )

    check_in = fields.Datetime(
        string="Entrada",
        tracking=True,
    )

    check_out = fields.Datetime(
        string="Salida",
        tracking=True,
    )

    attendance_ids = fields.Many2many(
        "hr.attendance",
        string="Asistencias de la semana",
        compute="_compute_attendance_ids",
    )

    type = fields.Selection(
        [
            ("extra", "Añadir horas extra al banco"),
            ("payment", "Pagar horas extra en nómina"),
            ("compensation", "Disfrutar horas extra como descanso"),
            ("early_exit", "Salida temprana"),
            ("adjustment", "Ajuste manual"),
        ],
        required=True,
        tracking=True,
    )

    attendance_id = fields.Many2one(
        "hr.attendance",
        tracking=True,
    )

    reference = fields.Char(
        tracking=True,
    )

    state = fields.Selection([
        ("draft", "Borrador"),
        ("done", "Confirmado"),
    ], default="draft", tracking=True)

    description = fields.Char(
        "Descripción",
        tracking=True,
    )

    attachment = fields.Binary(
        "Documento",
    )

    attachment_filename = fields.Char(
        "Nombre del archivo",
        tracking=True,
    )

    # =========================================================
    # LEGACY
    #
    # Se mantiene para los registros antiguos que generaban
    # hr.leave.allocation.
    #
    # Los nuevos registros ya NO crearán asignaciones.
    # =========================================================

    leave_allocation_id = fields.Many2one(
        "hr.leave.allocation",
        string="Asignación antigua",
        copy=False,
    )

    # =========================================================
    # COMPENSACIÓN DE HORAS
    # =========================================================

    compensation_date = fields.Date(
        string="Fecha de disfrute",
        help=(
            "Fecha en la que el empleado disfrutará las horas "
            "compensadas como ausencia."
        ),
    )

    compensation_leave_id = fields.Many2one(
        "hr.leave",
        string="Ausencia generada",
        readonly=True,
        copy=False,
    )

    # =========================================================
    # CÁLCULO
    # =========================================================

    signed_hours = fields.Float(
        string="Horas reales",
        compute="_compute_signed_hours",
        store=True,
    )

    expected_hours = fields.Float(
        string="Horas previstas",
        tracking=True,
        help=(
            "Horas que el empleado debía trabajar "
            "en el periodo calculado."
        ),
    )

    worked_hours = fields.Float(
        string="Horas trabajadas",
        tracking=True,
        help=(
            "Horas realmente trabajadas por el empleado "
            "en el periodo calculado."
        ),
    )

    difference_hours = fields.Float(
        string="Diferencia de horas",
        compute="_compute_difference_hours",
        store=True,
        readonly=True,
        tracking=True,
        help=(
            "Diferencia entre las horas trabajadas "
            "y las horas previstas."
        ),
    )

    # =========================================================
    # DETALLE DE ASISTENCIAS SEMANALES
    # =========================================================

    @api.depends(
        "employee_id",
        "date",
        "reference",
    )
    def _compute_attendance_ids(self):
        for rec in self:
            rec.attendance_ids = False

            if (
                rec.reference != "Attendance overtime week"
                or not rec.employee_id
                or not rec.date
            ):
                continue

            week_start = rec.date
            week_end = week_start + timedelta(days=6)

            timezone_name = (
                rec.employee_id.resource_calendar_id.tz
                or rec.env.user.tz
                or "UTC"
            )

            attendances = self.env[
                "hr.attendance"
            ].search([
                (
                    "employee_id",
                    "=",
                    rec.employee_id.id,
                ),
                ("check_in", "!=", False),
                ("check_out", "!=", False),
            ])

            week_attendances = self.env[
                "hr.attendance"
            ]

            for attendance in attendances:
                local_check_in = (
                    fields.Datetime.context_timestamp(
                        attendance.with_context(
                            tz=timezone_name
                        ),
                        attendance.check_in,
                    )
                )

                if (
                    week_start
                    <= local_check_in.date()
                    <= week_end
                ):
                    week_attendances |= attendance

            rec.attendance_ids = week_attendances

    # =========================================================
    # SALDO TOTAL
    # =========================================================

    def _get_total_balance(self, employee):
        entries = self.search([
            (
                "employee_id",
                "=",
                employee.id,
            ),
            (
                "state",
                "=",
                "done",
            ),
        ])

        return sum(
            rec._get_signed_hours()
            for rec in entries
        )

    # =========================================================
    # DIFERENCIA
    # =========================================================

    @api.depends(
        "expected_hours",
        "worked_hours",
    )
    def _compute_difference_hours(self):
        for rec in self:
            rec.difference_hours = (
                (rec.worked_hours or 0.0)
                - (rec.expected_hours or 0.0)
            )

    # =========================================================
    # CREATE
    # =========================================================

    @api.model_create_multi
    def create(self, vals_list):

        # -----------------------------------------------------
        # Reconstrucciones automáticas
        # -----------------------------------------------------

        if self.env.context.get(
            "skip_overtime_limit"
        ):
            records = super().create(
                vals_list
            )

            if not self.env.context.get(
                "skip_comp_sync"
            ):
                records._sync_compensation_leave()

            return records

        # -----------------------------------------------------
        # Validaciones de saldo
        # -----------------------------------------------------

        for vals in vals_list:
            new_state = vals.get(
                "state",
                "draft",
            )

            # Borrador no afecta al saldo.
            if new_state != "done":
                continue

            employee_id = vals.get(
                "employee_id"
            )

            if not employee_id:
                continue

            employee = self.env[
                "hr.employee"
            ].browse(
                employee_id
            ).exists()

            if not employee:
                continue

            new_type = vals.get("type")

            # -------------------------------------------------
            # Una compensación confirmada debe tener
            # fecha de disfrute.
            # -------------------------------------------------

            if (
                new_type == "compensation"
                and not vals.get("compensation_date")
            ):
                raise UserError(
                    "Debes indicar la fecha de disfrute "
                    "antes de confirmar una compensación "
                    "de horas extras."
                )

            simulated_entry = self.new(
                vals
            )

            current_balance = (
                self._get_total_balance(
                    employee
                )
            )

            added_hours = (
                simulated_entry._get_signed_hours()
            )

            future_balance = (
                current_balance
                + added_hours
            )

            if future_balance > self.MAX_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} "
                    f"horas acumuladas.\n\n"
                    f"Este movimiento modificaría "
                    f"el saldo en "
                    f"{round(added_hours, 2)} "
                    f"horas.\n\n"
                    f"El saldo final sería "
                    f"{round(future_balance, 2)} "
                    f"horas.\n\n"
                    f"No puede superar el límite de "
                    f"{self.MAX_HOURS} horas."
                )

            if future_balance < self.MIN_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} "
                    f"horas acumuladas.\n\n"
                    f"Este movimiento modificaría "
                    f"el saldo en "
                    f"{round(added_hours, 2)} "
                    f"horas.\n\n"
                    f"El saldo final sería "
                    f"{round(future_balance, 2)} "
                    f"horas.\n\n"
                    f"No puede bajar del límite de "
                    f"{self.MIN_HOURS} horas."
                )

        # -----------------------------------------------------
        # Crear
        # -----------------------------------------------------

        records = super().create(
            vals_list
        )

        type_labels = dict(
            self.env[
                "hr.overtime.entry"
            ]._fields[
                "type"
            ].selection
        )

        for rec in records:
            type_label = type_labels.get(
                rec.type,
                rec.type,
            )

            rec.employee_id.message_post(
                body=(
                    f"Registro creado: "
                    f"{rec.hours} horas "
                    f"({type_label})"
                ),
                subtype_xmlid="mail.mt_note",
            )

        # -----------------------------------------------------
        # Sincronizar ausencia de compensación
        # -----------------------------------------------------

        if not self.env.context.get(
            "skip_comp_sync"
        ):
            records._sync_compensation_leave()

        return records

    # =========================================================
    # WRITE
    # =========================================================

    def write(self, vals):

        if self.env.context.get(
            "skip_overtime_limit"
        ):
            return super().write(vals)

        old_values = {}

        for rec in self:
            old_values[rec.id] = {
                "employee_id": rec.employee_id,
                "hours": rec.hours,
                "type": rec.type,
                "state": rec.state,
            }

        # -----------------------------------------------------
        # Validación previa
        # -----------------------------------------------------

        for rec in self:

            new_employee = self.env[
                "hr.employee"
            ].browse(
                vals.get(
                    "employee_id",
                    rec.employee_id.id,
                )
            ).exists()

            new_hours = vals.get(
                "hours",
                rec.hours,
            )

            new_type = vals.get(
                "type",
                rec.type,
            )

            new_state = vals.get(
                "state",
                rec.state,
            )

            new_compensation_date = vals.get(
                "compensation_date",
                rec.compensation_date,
            )

            if (
                new_type == "compensation"
                and new_state == "done"
                and not new_compensation_date
            ):
                raise UserError(
                    "Debes indicar la fecha de disfrute "
                    "antes de confirmar una compensación "
                    "de horas extras."
                )

            if (
                not new_employee
                or new_state != "done"
            ):
                continue

            simulated_entry = self.new({
                "employee_id": (
                    new_employee.id
                ),
                "hours": new_hours,
                "type": new_type,
                "state": new_state,
            })

            new_signed_hours = (
                simulated_entry
                ._get_signed_hours()
            )

            current_balance = (
                self._get_total_balance(
                    new_employee
                )
            )

            previous_effect = 0.0

            # Si el registro ya estaba confirmado
            # quitamos primero su efecto anterior.
            if (
                rec.state == "done"
                and rec.employee_id
                == new_employee
            ):
                previous_effect = (
                    rec._get_signed_hours()
                )

            future_balance = (
                current_balance
                - previous_effect
                + new_signed_hours
            )

            if future_balance > self.MAX_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} "
                    f"horas acumuladas.\n\n"
                    f"El nuevo saldo sería "
                    f"{round(future_balance, 2)} "
                    f"horas.\n\n"
                    f"No puede superar el límite de "
                    f"{self.MAX_HOURS} horas."
                )

            if future_balance < self.MIN_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} "
                    f"horas acumuladas.\n\n"
                    f"El nuevo saldo sería "
                    f"{round(future_balance, 2)} "
                    f"horas.\n\n"
                    f"No puede bajar del límite de "
                    f"{self.MIN_HOURS} horas."
                )

        # -----------------------------------------------------
        # Escribir
        # -----------------------------------------------------

        result = super().write(
            vals
        )

        type_labels = dict(
            self.env[
                "hr.overtime.entry"
            ]._fields[
                "type"
            ].selection
        )

        # -----------------------------------------------------
        # LOG
        # -----------------------------------------------------

        for rec in self:
            old = old_values.get(
                rec.id,
                {},
            )

            changes = []

            if "hours" in vals:
                changes.append(
                    f"Horas: "
                    f"{old.get('hours', 0.0)} "
                    f"→ {rec.hours}"
                )

            if "type" in vals:
                old_type = type_labels.get(
                    old.get("type"),
                    old.get("type"),
                )

                new_type = type_labels.get(
                    rec.type,
                    rec.type,
                )

                changes.append(
                    f"Tipo: "
                    f"{old_type} "
                    f"→ {new_type}"
                )

            if "state" in vals:
                changes.append(
                    f"Estado: "
                    f"{old.get('state', '')} "
                    f"→ {rec.state}"
                )

            if "compensation_date" in vals:
                changes.append(
                    "Fecha de disfrute: "
                    f"{rec.compensation_date or '-'}"
                )

            if changes:
                rec.employee_id.message_post(
                    body=(
                        "Actualización overtime: "
                        + " | ".join(changes)
                    ),
                    subtype_xmlid="mail.mt_note",
                )

        # -----------------------------------------------------
        # SINCRONIZAR AUSENCIA
        # -----------------------------------------------------

        if (
            not self.env.context.get(
                "skip_comp_sync"
            )
            and any(
                field_name in vals
                for field_name in [
                    "hours",
                    "employee_id",
                    "type",
                    "state",
                    "date",
                    "compensation_date",
                ]
            )
        ):
            self._sync_compensation_leave()

        return result

    # =========================================================
    # CONFIRMAR
    # =========================================================

    def action_confirm(self):
        for rec in self:

            if (
                rec.type == "compensation"
                and not rec.compensation_date
            ):
                raise UserError(
                    "Debes indicar la fecha de disfrute "
                    "antes de confirmar un descanso "
                    "por horas extra."
                )

        self.with_context(
            skip_comp_sync=True
        ).write({
            "state": "done",
        })

        # Seguridad por si quedaba una asignación del sistema viejo.
        self._cleanup_legacy_compensation_allocation()

        # Sistema nuevo.
        self._sync_compensation_leave()

        for rec in self:
            rec.message_post(
                body=(
                    f"Registro confirmado: "
                    f"{rec.hours} horas ({rec.type})"
                )
            )

        return True

    # =========================================================
    # VOLVER A BORRADOR
    # =========================================================

    def action_set_to_draft(self):
        self.with_context(
            skip_comp_sync=True
        ).write({
            "state": "draft",
        })

        # Si había una ausencia generada con el sistema nuevo,
        # desaparece mientras el movimiento está en borrador.
        self._delete_generated_compensation_leave()

        # Si era un registro histórico, limpiamos su antigua
        # asignación automática.
        self._cleanup_legacy_compensation_allocation()

        return True

    # =========================================================
    # TIPO DE AUSENCIA DE COMPENSACIÓN
    # =========================================================

    def _get_compensation_leave_type(self):
        """
        Obtiene el tipo de ausencia configurado expresamente
        para las compensaciones de Overtime.

        Ya no buscamos el primer hr.leave.type disponible.
        """

        config = self.env.ref(
            "sb_hr_overtime_bank_pro."
            "vacation_config_default",
            raise_if_not_found=False,
        )

        if not config:
            return self.env[
                "hr.leave.type"
            ]

        return (
            config.compensation_leave_type_id
        )

    # =========================================================
    # VALIDAR AUSENCIA GENERADA
    # =========================================================

    def _validate_generated_leave(
        self,
        leave,
    ):
        if not leave:
            return

        # Odoo dispone internamente de
        # _action_validate().
        if hasattr(
            leave,
            "_action_validate",
        ):
            leave._action_validate()
            return

        # Fallback por compatibilidad.
        if (
            hasattr(leave, "action_confirm")
            and leave.state == "draft"
        ):
            leave.action_confirm()

        if (
            hasattr(leave, "action_approve")
            and leave.state == "confirm"
        ):
            leave.action_approve()

        if (
            hasattr(leave, "action_validate")
            and leave.state != "validate"
        ):
            leave.action_validate()
            return

        if "state" in leave._fields:
            leave.write({
                "state": "validate",
            })

    # =========================================================
    # SINCRONIZAR COMPENSACIÓN → AUSENCIA
    # =========================================================

    def _sync_compensation_leave(self):

        Leave = self.env[
            "hr.leave"
        ].sudo()

        for rec in self:

            existing_leave = (
                rec.compensation_leave_id.sudo()
            )

            needs_leave = (
                rec.type == "compensation"
                and rec.state == "done"
                and rec.employee_id
                and abs(rec.hours or 0.0) > 0.0
            )

            # -------------------------------------------------
            # Ya no necesita ausencia:
            # eliminar únicamente la que generó este registro.
            # -------------------------------------------------

            if not needs_leave:

                if existing_leave:

                    rec.with_context(
                        skip_comp_sync=True
                    ).write({
                        "compensation_leave_id": False,
                    })

                    existing_leave.unlink()

                continue

            # -------------------------------------------------
            # Fecha obligatoria
            # -------------------------------------------------

            if not rec.compensation_date:
                raise UserError(
                    "Debes indicar la fecha de disfrute "
                    "para la compensación de horas extra."
                )

            # -------------------------------------------------
            # Tipo de ausencia configurado
            # -------------------------------------------------

            leave_type = (
                rec._get_compensation_leave_type()
            )

            if not leave_type:
                raise UserError(
                    "No hay configurado un tipo de "
                    "ausencia para las compensaciones "
                    "de horas extra.\n\n"
                    "Ve a Overtime > "
                    "Configuración vacaciones y "
                    "selecciona el tipo correspondiente."
                )

            # -------------------------------------------------
            # IMPORTANTE
            #
            # El nuevo tipo de ausencia NO debe necesitar
            # asignaciones, porque el saldo real ya está
            # gestionado por Overtime Bank.
            # -------------------------------------------------

            if (
                "requires_allocation"
                in leave_type._fields
                and leave_type.requires_allocation
                == "yes"
            ):
                raise UserError(
                    "El tipo de ausencia configurado "
                    "para compensaciones requiere una "
                    "asignación previa.\n\n"
                    "Para el nuevo funcionamiento de "
                    "Overtime debe utilizarse un tipo "
                    "de ausencia que NO requiera "
                    "asignación."
                )
                
            # -------------------------------------------------
            # IMPORTANTE 2
            #
            # Tampoco debe utilizar el banco nativo de
            # horas extra de Odoo.
            # -------------------------------------------------

            if (
                "overtime_deductible" in leave_type._fields
                and leave_type.overtime_deductible
            ):
                raise UserError(
                    "El tipo de ausencia seleccionado tiene activada "
                    "la deducción nativa de horas extra de Odoo.\n\n"
                    "Debes desactivarla o seleccionar un tipo específico "
                    "para Overtime Bank."
                )

            # -------------------------------------------------
            # Comprobar que hablamos de un día completo
            # -------------------------------------------------

            calendar = (
                rec.employee_id
                .resource_calendar_id
            )

            hours_per_day = (
                calendar.hours_per_day
                if calendar
                else 8.0
            ) or 8.0

            compensation_hours = abs(
                rec.hours or 0.0
            )

            if abs(
                compensation_hours
                - hours_per_day
            ) > 0.05:
                raise UserError(
                    "La generación automática de "
                    "ausencias está preparada "
                    "actualmente para compensaciones "
                    "de un día completo.\n\n"
                    f"Horas por día del empleado: "
                    f"{hours_per_day:.2f} h.\n"
                    f"Horas compensadas: "
                    f"{compensation_hours:.2f} h.\n\n"
                    "Si necesitas una compensación "
                    "parcial, registra la ausencia "
                    "manualmente."
                )

            # -------------------------------------------------
            # Valores de la ausencia
            # -------------------------------------------------

            values = {
                "name": (
                    "Compensación horas extras - "
                    f"{rec.employee_id.name or ''}"
                ),
                "employee_id": (
                    rec.employee_id.id
                ),
                "holiday_status_id": (
                    leave_type.id
                ),
                "request_date_from": (
                    rec.compensation_date
                ),
                "request_date_to": (
                    rec.compensation_date
                ),
            }

            # -------------------------------------------------
            # Si ya existe una ausencia generada,
            # la actualizamos.
            # -------------------------------------------------

            if existing_leave:

                # Una ausencia validada normalmente
                # no debe modificarse directamente.
                if (
                    existing_leave.state
                    == "validate"
                ):
                    if hasattr(
                        existing_leave,
                        "action_draft",
                    ):
                        existing_leave.action_draft()
                    else:
                        # Si no existe action_draft,
                        # recreamos la ausencia.
                        rec.with_context(
                            skip_comp_sync=True
                        ).write({
                            "compensation_leave_id": False,
                        })

                        existing_leave.unlink()
                        existing_leave = False

                if existing_leave:
                    existing_leave.write(
                        values
                    )

            # -------------------------------------------------
            # Crear
            # -------------------------------------------------

            if not existing_leave:

                existing_leave = (
                    Leave.create(values)
                )

                rec.with_context(
                    skip_comp_sync=True
                ).write({
                    "compensation_leave_id": (
                        existing_leave.id
                    ),
                })

            # -------------------------------------------------
            # Aprobar directamente
            # -------------------------------------------------

            rec._validate_generated_leave(
                existing_leave
            )

    # =========================================================
    # HORAS CON SIGNO
    # =========================================================

    def _get_signed_hours(self):
        self.ensure_one()

        if self.state != "done":
            return 0.0

        if self.type == "extra":
            return self.hours

        if self.type in (
            "early_exit",
            "payment",
            "compensation",
        ):
            return -abs(
                self.hours
            )

        if self.type == "adjustment":
            return self.hours

        return 0.0

    @api.depends(
        "hours",
        "type",
        "state",
    )
    def _compute_signed_hours(self):
        for rec in self:
            rec.signed_hours = (
                rec._get_signed_hours()
            )

    # =========================================================
    # ELIMINAR
    # =========================================================

    def unlink(self):

        for rec in self:

            type_label = dict(
                self._fields[
                    "type"
                ].selection
            ).get(
                rec.type
            )

            # -------------------------------------------------
            # LOG ANTES DE BORRAR
            # -------------------------------------------------

            rec.employee_id.message_post(
                body=(
                    f"Overtime eliminado: "
                    f"{rec.hours}h "
                    f"({type_label})"
                )
            )

            # -------------------------------------------------
            # NUEVO SISTEMA:
            # eliminar ausencia generada.
            # -------------------------------------------------

            compensation_leave = (
                rec.compensation_leave_id.sudo()
            )

            if compensation_leave:

                rec.with_context(
                    skip_comp_sync=True
                ).write({
                    "compensation_leave_id": False,
                })

                compensation_leave.unlink()

            # -------------------------------------------------
            # LEGACY:
            # eliminar asignación antigua únicamente si
            # pertenecía directamente a este registro.
            # -------------------------------------------------

            allocation = (
                rec.leave_allocation_id.sudo()
            )

            if allocation:

                rec.with_context(
                    skip_comp_sync=True
                ).write({
                    "leave_allocation_id": False,
                })

                allocation.unlink()

        return super().unlink()
    
    def _cleanup_legacy_compensation_allocation(self):
        """
        El sistema antiguo creaba una hr.leave.allocation
        al confirmar una compensación.

        Eliminamos únicamente la asignación enlazada directamente
        a este movimiento Overtime.
        """

        for rec in self:

            if (
                rec.type != "compensation"
                or not rec.leave_allocation_id
            ):
                continue

            allocation = (
                rec.leave_allocation_id.sudo()
            )

            # Primero quitamos el enlace.
            rec.with_context(
                skip_comp_sync=True,
                skip_overtime_limit=True,
            ).write({
                "leave_allocation_id": False,
            })

            # Si está aprobada intentamos rechazarla
            # antes de eliminar.
            if (
                allocation.state == "validate"
                and hasattr(
                    allocation,
                    "action_refuse",
                )
            ):
                try:
                    allocation.sudo().action_refuse()
                except Exception:
                    pass

            allocation.sudo().unlink()