from odoo import models, fields, api
from datetime import datetime, time


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_entry_id = fields.Many2one("hr.overtime.entry")

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._sync_overtime_day()
        return rec

    def write(self, vals):
        old_days = []
        for rec in self:
            if rec.employee_id and rec.check_in:
                old_days.append((rec.employee_id.id, rec.check_in.date()))

        res = super().write(vals)

        days = set(old_days)
        for rec in self:
            if rec.employee_id and rec.check_in:
                days.add((rec.employee_id.id, rec.check_in.date()))

        for employee_id, day in days:
            self._sync_overtime_for_employee_day(employee_id, day)

        return res

    def unlink(self):
        days = []
        for rec in self:
            if rec.employee_id and rec.check_in:
                days.append((rec.employee_id.id, rec.check_in.date()))

        res = super().unlink()

        for employee_id, day in set(days):
            self._sync_overtime_for_employee_day(employee_id, day)

        return res

    def _sync_overtime_day(self):
        for rec in self:
            if rec.employee_id and rec.check_in:
                rec._sync_overtime_for_employee_day(
                    rec.employee_id.id,
                    rec.check_in.date()
                )

    def _get_attendance_overtime_value(self, attendance):
        if "overtime_hours" in attendance._fields:
            return attendance.overtime_hours or 0.0
        if "extra_hours" in attendance._fields:
            return attendance.extra_hours or 0.0
        return 0.0

    def _sync_overtime_for_employee_day(self, employee_id, day):
        Overtime = self.env["hr.overtime.entry"]

        start_dt = datetime.combine(day, time.min)
        end_dt = datetime.combine(day, time.max)

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
            ("reference", "=", "Attendance overtime"),
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
            "reference": "Attendance overtime",
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