from datetime import datetime, timedelta, time

import pytz

from odoo import api, fields, models


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_entry_id = fields.Many2one(
        "hr.overtime.entry",
        string="Overtime Entry",
        copy=False,
    )
    
    attendance_local_date = fields.Date(
        string="Fecha",
        compute="_compute_attendance_local_values",
    )

    attendance_local_check_in = fields.Char(
        string="Entrada",
        compute="_compute_attendance_local_values",
    )

    attendance_local_check_out = fields.Char(
        string="Salida",
        compute="_compute_attendance_local_values",
    )

    AUTO_REF_OLD = "Attendance overtime"
    AUTO_REF_DAY = "Attendance overtime day"
    AUTO_REF_WEEK = "Attendance overtime week"



    @api.depends(
        "check_in",
        "check_out",
        "employee_id",
        "employee_id.resource_calendar_id",
    )
    def _compute_attendance_local_values(self):
        for rec in self:

            rec.attendance_local_date = False
            rec.attendance_local_check_in = False
            rec.attendance_local_check_out = False

            timezone_name = (
                rec.employee_id.resource_calendar_id.tz
                if rec.employee_id
                and rec.employee_id.resource_calendar_id
                else False
            )

            timezone_name = (
                timezone_name
                or self.env.user.tz
                or "UTC"
            )

            if rec.check_in:
                local_check_in = fields.Datetime.context_timestamp(
                    rec.with_context(tz=timezone_name),
                    rec.check_in,
                )

                rec.attendance_local_date = local_check_in.date()

                rec.attendance_local_check_in = (
                    local_check_in.strftime("%H:%M")
                )

            if rec.check_out:
                local_check_out = fields.Datetime.context_timestamp(
                    rec.with_context(tz=timezone_name),
                    rec.check_out,
                )

                rec.attendance_local_check_out = (
                    local_check_out.strftime("%H:%M")
                )

    @api.model
    def create(self, vals):
        attendance = super().create(vals)
        attendance._sync_overtime_period()
        return attendance

    def write(self, vals):
        affected_periods = set()

        # Guardamos el empleado y el día anteriores a la modificación.
        for attendance in self:
            if attendance.employee_id and attendance.check_in:
                affected_periods.add(
                    (
                        attendance.employee_id.id,
                        attendance._get_local_day(),
                    )
                )

        result = super().write(vals)

        # Guardamos también el empleado y el día posteriores.
        for attendance in self:
            if attendance.employee_id and attendance.check_in:
                affected_periods.add(
                    (
                        attendance.employee_id.id,
                        attendance._get_local_day(),
                    )
                )

        for employee_id, local_day in affected_periods:
            self._sync_overtime_for_employee_period(
                employee_id,
                local_day,
            )

        return result

    def unlink(self):
        affected_periods = set()

        # Guardamos los periodos antes de eliminar las asistencias.
        for attendance in self:
            if attendance.employee_id and attendance.check_in:
                affected_periods.add(
                    (
                        attendance.employee_id.id,
                        attendance._get_local_day(),
                    )
                )

        result = super().unlink()

        for employee_id, local_day in affected_periods:
            self._sync_overtime_for_employee_period(
                employee_id,
                local_day,
            )

        return result

    def _get_attendance_overtime_value(self, attendance):
        if "overtime_hours" in attendance._fields:
            return attendance.overtime_hours or 0.0

        if "extra_hours" in attendance._fields:
            return attendance.extra_hours or 0.0

        return 0.0

    def _get_employee_tz(self, employee):
        if employee.resource_calendar_id.tz:
            return employee.resource_calendar_id.tz

        if self.env.user.tz:
            return self.env.user.tz

        return "UTC"

    def _get_local_day(self):
        self.ensure_one()

        if not self.check_in:
            return False

        timezone_name = self._get_employee_tz(self.employee_id)

        local_datetime = fields.Datetime.context_timestamp(
            self.with_context(tz=timezone_name),
            self.check_in,
        )

        return local_datetime.date()

    def _get_utc_day_range(self, employee, day):
        timezone_name = self._get_employee_tz(employee)
        timezone = pytz.timezone(timezone_name)

        local_start = timezone.localize(
            datetime.combine(day, time.min)
        )

        local_end = timezone.localize(
            datetime.combine(day, time.max)
        )

        utc_start = (
            local_start
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        utc_end = (
            local_end
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        return utc_start, utc_end

    def _get_week_range(self, local_day):

        week_start = local_day - timedelta(
            days=local_day.weekday()
        )

        week_end = week_start + timedelta(days=6)

        return week_start, week_end
    
    def _format_hours(self, hours):
        hours = hours or 0.0

        sign = "-" if hours < 0 else ""
        total_minutes = round(abs(hours) * 60)

        hour_part, minute_part = divmod(total_minutes, 60)

        return f"{sign}{hour_part:02d}:{minute_part:02d}"

    def _get_utc_week_range(
        self,
        employee,
        week_start,
        week_end,
    ):

        timezone_name = self._get_employee_tz(employee)
        timezone = pytz.timezone(timezone_name)

        local_start = timezone.localize(
            datetime.combine(week_start, time.min)
        )

        local_end = timezone.localize(
            datetime.combine(week_end, time.max)
        )

        utc_start = (
            local_start
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        utc_end = (
            local_end
            .astimezone(pytz.UTC)
            .replace(tzinfo=None)
        )

        return utc_start, utc_end
    
    def _get_expected_hours_for_day(
        self,
        employee,
        day,
    ):
        calendar = employee.resource_calendar_id
        resource = employee.resource_id

        if not calendar or not resource or not day:
            return 0.0

        timezone_name = self._get_employee_tz(employee)
        timezone = pytz.timezone(timezone_name)

        local_start = timezone.localize(
            datetime.combine(day, time.min)
        )

        local_end = timezone.localize(
            datetime.combine(
                day + timedelta(days=1),
                time.min,
            )
        )

        intervals_by_resource = calendar._work_intervals_batch(
            local_start,
            local_end,
            resources=resource,
        )

        intervals = (
            intervals_by_resource.get(resource.id)
            or intervals_by_resource.get(resource)
            or []
        )

        expected_hours = 0.0

        for interval in intervals:
            interval_start = interval[0]
            interval_end = interval[1]

            expected_hours += (
                interval_end - interval_start
            ).total_seconds() / 3600.0

        return round(expected_hours, 4)
    
    def _get_worked_hours_for_day(
        self,
        employee,
        day,
    ):
        utc_start, utc_end = self._get_utc_day_range(
            employee,
            day,
        )

        attendances = self.search([
            ("employee_id", "=", employee.id),
            (
                "check_in",
                ">=",
                fields.Datetime.to_string(utc_start),
            ),
            (
                "check_in",
                "<=",
                fields.Datetime.to_string(utc_end),
            ),
            ("check_out", "!=", False),
        ])

        worked_hours = sum(
            attendances.mapped("worked_hours")
        )

        return round(worked_hours, 4)


    def _sync_overtime_period(self):
        affected_periods = set()

        for attendance in self:
            if not attendance.employee_id or not attendance.check_in:
                continue

            local_day = attendance._get_local_day()

            if not local_day:
                continue

            affected_periods.add(
                (
                    attendance.employee_id.id,
                    local_day,
                )
            )

            affected_periods.add(
                (
                    attendance.employee_id.id,
                    local_day - timedelta(days=1),
                )
            )

        for employee_id, local_day in affected_periods:
            self._sync_overtime_for_employee_period(
                employee_id,
                local_day,
            )

    def _sync_overtime_for_employee_period(
        self,
        employee_id,
        local_day,
    ):

        employee = self.env["hr.employee"].browse(
            employee_id
        ).exists()

        if not employee or not local_day:
            return

        calculation_mode = (
            employee.overtime_calculation_mode or "daily"
        )

        if calculation_mode == "weekly":
            return self._sync_overtime_for_employee_week(
                employee.id,
                local_day,
            )

        return self._sync_overtime_for_employee_day(
            employee.id,
            local_day,
        )

    def _sync_overtime_for_employee_day(
        self,
        employee_id,
        day,
    ):
        OvertimeEntry = self.env["hr.overtime.entry"]

        employee = self.env["hr.employee"].browse(
            employee_id
        ).exists()

        if not employee or not day:
            return

        week_start, _week_end = self._get_week_range(day)

        # Si el empleado está en modo diario, eliminamos cualquier
        # registro semanal automático de esa semana.
        weekly_entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", "=", week_start),
            ("reference", "=", self.AUTO_REF_WEEK),
        ])

        if weekly_entries:
            weekly_entries.unlink()

        existing_entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", "=", day),
            ("reference", "=", self.AUTO_REF_DAY),
        ], order="id asc")

        main_entry = existing_entries[:1]
        duplicate_entries = existing_entries[1:]

        if duplicate_entries:
            duplicate_entries.unlink()

        today = fields.Date.context_today(self)

        # No consolidamos el día actual ni fechas futuras.
        # Así una jornada partida no genera un -04:00 después
        # del fichaje de la mañana.
        if day >= today:
            if main_entry:
                main_entry.unlink()

            return

        expected_hours = self._get_expected_hours_for_day(
            employee,
            day,
        )

        worked_hours = self._get_worked_hours_for_day(
            employee,
            day,
        )

        difference = round(
            worked_hours - expected_hours,
            4,
        )

        # Día no laborable y sin asistencias.
        if expected_hours == 0.0 and worked_hours == 0.0:
            if main_entry:
                main_entry.unlink()

            return

        # No existe diferencia relevante.
        if abs(difference) < 0.01:
            if main_entry:
                main_entry.unlink()

            return

        if difference > 0:
            entry_type = "extra"
            entry_hours = difference
        else:
            entry_type = "early_exit"
            entry_hours = abs(difference)

        values = {
            "employee_id": employee.id,
            "date": day,
            "hours": entry_hours,
            "type": entry_type,
            "state": "done",
            "reference": self.AUTO_REF_DAY,
            "expected_hours": expected_hours,
            "worked_hours": worked_hours,
            "description": (
                "Movimiento diario automático.\n"
                f"Horas trabajadas: "
                f"{self._format_hours(worked_hours)}\n"
                f"Horas previstas: "
                f"{self._format_hours(expected_hours)}\n"
                f"Diferencia: "
                f"{self._format_hours(difference)}"
            ),
        }

        context_values = {
            "skip_overtime_limit": True,
            "skip_comp_sync": True,
        }

        if main_entry:
            main_entry.with_context(
                **context_values
            ).write(values)
        else:
            OvertimeEntry.with_context(
                **context_values
            ).create(values)

    def _get_expected_hours_for_week(
        self,
        employee,
        week_start,
        week_end,
    ):

        calendar = employee.resource_calendar_id
        resource = employee.resource_id

        if not calendar or not resource:
            return 0.0

        timezone_name = self._get_employee_tz(employee)
        timezone = pytz.timezone(timezone_name)

        local_start = timezone.localize(
            datetime.combine(week_start, time.min)
        )

        # El final se establece al comienzo del día siguiente.
        # _work_intervals_batch trabaja mejor con rangos [inicio, fin).
        local_end = timezone.localize(
            datetime.combine(
                week_end + timedelta(days=1),
                time.min,
            )
        )

        intervals_by_resource = calendar._work_intervals_batch(
            local_start,
            local_end,
            resources=resource,
        )

        # Compatibilidad con posibles claves resource.id o resource.
        intervals = (
            intervals_by_resource.get(resource.id)
            or intervals_by_resource.get(resource)
            or []
        )

        expected_hours = 0.0

        for interval in intervals:
            interval_start = interval[0]
            interval_end = interval[1]

            expected_hours += (
                interval_end - interval_start
            ).total_seconds() / 3600.0

        return round(expected_hours, 4)

    def _get_worked_hours_for_week(
        self,
        employee,
        week_start,
        week_end,
    ):

        utc_start, utc_end = self._get_utc_week_range(
            employee,
            week_start,
            week_end,
        )

        attendances = self.search([
            ("employee_id", "=", employee.id),
            (
                "check_in",
                ">=",
                fields.Datetime.to_string(utc_start),
            ),
            (
                "check_in",
                "<=",
                fields.Datetime.to_string(utc_end),
            ),
            ("check_out", "!=", False),
        ])

        worked_hours = sum(
            attendances.mapped("worked_hours")
        )

        return round(worked_hours, 4)

    def _sync_overtime_for_employee_week(
        self,
        employee_id,
        local_day,
    ):

        OvertimeEntry = self.env["hr.overtime.entry"]

        employee = self.env["hr.employee"].browse(
            employee_id
        ).exists()

        if not employee or not local_day:
            return

        week_start, week_end = self._get_week_range(local_day)
        today = fields.Date.context_today(self)

        weekly_entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", "=", week_start),
            ("reference", "=", self.AUTO_REF_WEEK),
        ], order="id asc")

        weekly_entry = weekly_entries[:1]
        duplicate_entries = weekly_entries[1:]

        if duplicate_entries:
            duplicate_entries.unlink()

        # No consolidamos la semana que todavía está en curso.
        if week_end >= today:
            if weekly_entry:
                weekly_entry.unlink()

            # También eliminamos posibles movimientos diarios,
            # ya que el empleado trabaja en modo semanal.
            current_daily_entries = OvertimeEntry.search([
                ("employee_id", "=", employee.id),
                ("date", ">=", week_start),
                ("date", "<=", week_end),
                (
                    "reference",
                    "in",
                    [
                        self.AUTO_REF_OLD,
                        self.AUTO_REF_DAY,
                    ],
                ),
            ])

            if current_daily_entries:
                current_daily_entries.unlink()

            return

        daily_entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", ">=", week_start),
            ("date", "<=", week_end),
            (
                "reference",
                "in",
                [
                    self.AUTO_REF_OLD,
                    self.AUTO_REF_DAY,
                ],
            ),
        ])

        if daily_entries:
            daily_entries.unlink()

        expected_hours = self._get_expected_hours_for_week(
            employee,
            week_start,
            week_end,
        )

        worked_hours = self._get_worked_hours_for_week(
            employee,
            week_start,
            week_end,
        )

        difference = round(
            worked_hours - expected_hours,
            4,
        )

        if abs(difference) < 0.01:
            if weekly_entry:
                weekly_entry.unlink()

            return

        if difference > 0:
            entry_type = "extra"
            entry_hours = difference
        else:
            entry_type = "early_exit"
            entry_hours = abs(difference)

        values = {
            "employee_id": employee.id,
            "date": week_start,
            "type": entry_type,
            "hours": entry_hours,
            "state": "done",
            "reference": self.AUTO_REF_WEEK,
            "expected_hours": expected_hours,
            "worked_hours": worked_hours,
            "description": (
                f"Resumen semanal ({week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')})\n"
                f"Horas trabajadas: {self._format_hours(worked_hours)}\n"
                f"Horas previstas: {self._format_hours(expected_hours)}\n"
                f"Diferencia: {self._format_hours(difference)}"
            ),
        }

        context_values = {
            "skip_overtime_limit": True,
            "skip_comp_sync": True,
        }

        if weekly_entry:
            weekly_entry.with_context(
                **context_values
            ).write(values)
        else:
            OvertimeEntry.with_context(
                **context_values
            ).create(values)

    @api.model
    def rebuild_attendance_overtime_entries(self):
        """
        Elimina todos los movimientos automáticos de asistencias
        y los vuelve a generar según el modo de cada empleado.
        """
        OvertimeEntry = self.env["hr.overtime.entry"]

        automatic_entries = OvertimeEntry.search([
            "|",
            (
                "reference",
                "in",
                [
                    self.AUTO_REF_OLD,
                    self.AUTO_REF_DAY,
                    self.AUTO_REF_WEEK,
                ],
            ),
            ("attendance_id", "!=", False),
        ])

        if automatic_entries:
            automatic_entries.unlink()

        affected_periods = set()

        attendances = self.search([
            ("check_out", "!=", False),
            ("employee_id", "!=", False),
            ("check_in", "!=", False),
        ])

        for attendance in attendances:
            local_day = attendance._get_local_day()

            if local_day:
                affected_periods.add(
                    (
                        attendance.employee_id.id,
                        local_day,
                    )
                )

        for employee_id, local_day in affected_periods:
            self._sync_overtime_for_employee_period(
                employee_id,
                local_day,
            )

        return True