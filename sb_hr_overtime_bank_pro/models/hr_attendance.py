from odoo import models, fields, api
from datetime import datetime, time
import pytz


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_entry_id = fields.Many2one("hr.overtime.entry")

    AUTO_REF_OLD = "Attendance overtime"
    AUTO_REF_DAY = "Attendance overtime day"

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._sync_overtime_day()
        return rec

    def write(self, vals):
        days = set()

        for rec in self:
            if rec.employee_id and rec.check_in:
                days.add((rec.employee_id.id, rec._get_local_day()))

        res = super().write(vals)

        for rec in self:
            if rec.employee_id and rec.check_in:
                days.add((rec.employee_id.id, rec._get_local_day()))

        for employee_id, day in days:
            self._sync_overtime_for_employee_day(employee_id, day)

        return res

    def unlink(self):
        days = set()

        for rec in self:
            if rec.employee_id and rec.check_in:
                days.add((rec.employee_id.id, rec._get_local_day()))

        res = super().unlink()

        for employee_id, day in days:
            self._sync_overtime_for_employee_day(employee_id, day)

        return res

    def _get_attendance_overtime_value(self, attendance):
        if "overtime_hours" in attendance._fields:
            return attendance.overtime_hours or 0.0
        if "extra_hours" in attendance._fields:
            return attendance.extra_hours or 0.0
        return 0.0

    def _get_employee_tz(self, employee):
        return employee.resource_calendar_id.tz or self.env.user.tz or "UTC"

    def _get_local_day(self):
        self.ensure_one()
        tz_name = self._get_employee_tz(self.employee_id)
        dt = fields.Datetime.context_timestamp(
            self.with_context(tz=tz_name),
            self.check_in
        )
        return dt.date()

    def _get_utc_day_range(self, employee, day):
        tz_name = self._get_employee_tz(employee)
        tz = pytz.timezone(tz_name)

        local_start = tz.localize(datetime.combine(day, time.min))
        local_end = tz.localize(datetime.combine(day, time.max))

        utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)

        return utc_start, utc_end

    def _sync_overtime_day(self):
        for rec in self:
            if rec.employee_id and rec.check_in:
                rec._sync_overtime_for_employee_day(
                    rec.employee_id.id,
                    rec._get_local_day()
                )

    def _sync_overtime_for_employee_day(self, employee_id, day):
        Overtime = self.env["hr.overtime.entry"]
        employee = self.env["hr.employee"].browse(employee_id)

        start_dt, end_dt = self._get_utc_day_range(employee, day)

        attendances = self.search([
            ("employee_id", "=", employee_id),
            ("check_in", ">=", fields.Datetime.to_string(start_dt)),
            ("check_in", "<=", fields.Datetime.to_string(end_dt)),
            ("check_out", "!=", False),
        ])

        overtime_total = sum(
            self._get_attendance_overtime_value(att)
            for att in attendances
        )

        existing_entries = Overtime.search([
            ("employee_id", "=", employee_id),
            ("date", "=", day),
            ("reference", "=", self.AUTO_REF_DAY),
        ])

        if abs(overtime_total) < 0.01:
            existing_entries.unlink()
            return

        entry_type = "extra" if overtime_total > 0 else "early_exit"
        hours = abs(overtime_total)

        values = {
            "employee_id": employee_id,
            "date": day,
            "hours": hours,
            "type": entry_type,
            "state": "done",
            "reference": self.AUTO_REF_DAY,
        }

        main_entry = existing_entries[:1]

        if main_entry:
            main_entry.with_context(
                skip_overtime_limit=True,
                skip_comp_sync=True,
            ).write(values)

            duplicates = existing_entries - main_entry
            if duplicates:
                duplicates.unlink()
        else:
            Overtime.with_context(
                skip_overtime_limit=True,
                skip_comp_sync=True,
            ).create(values)

    @api.model
    def rebuild_attendance_overtime_entries(self):
        Overtime = self.env["hr.overtime.entry"]

        # Solo borra automáticos antiguos/nuevos.
        auto_entries = Overtime.search([
            "|",
            ("reference", "in", [self.AUTO_REF_OLD, self.AUTO_REF_DAY]),
            ("attendance_id", "!=", False),
        ])
        auto_entries.unlink()

        days = set()

        attendances = self.search([
            ("check_out", "!=", False),
            ("employee_id", "!=", False),
            ("check_in", "!=", False),
        ])

        for att in attendances:
            days.add((att.employee_id.id, att._get_local_day()))

        for employee_id, day in days:
            self._sync_overtime_for_employee_day(employee_id, day)

        return True