from odoo import models, fields, api

class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_entry_id = fields.Many2one("hr.overtime.entry")

    @property
    def _overtime_source_date(self):
        self.ensure_one()
        source_dt = self.check_out or self.check_in
        return source_dt.date() if source_dt else False

    @api.model
    def create(self, vals):
        rec = super().create(vals)
        rec._sync_overtime()
        return rec

    def write(self, vals):
        res = super().write(vals)
        for rec in self:
            rec._sync_overtime()
        return res

    def _sync_overtime(self):
        OvertimeEntry = self.env["hr.overtime.entry"]

        for rec in self:
            overtime = rec.overtime_hours or 0.0

            if not rec.employee_id or not rec._overtime_source_date:
                continue

            if overtime == 0:
                if rec.overtime_entry_id:
                    rec.overtime_entry_id.unlink()
                    rec.overtime_entry_id = False
                continue

            entry_type = "extra" if overtime > 0 else "early_exit"
            hours = abs(overtime)

            values = {
                "employee_id": rec.employee_id.id,
                "date": rec._overtime_source_date,
                "hours": hours,
                "attendance_id": rec.id,
                "reference": "Attendance overtime",
                "type": entry_type,
                "state": "done",
            }

            if rec.overtime_entry_id:
                rec.overtime_entry_id.write(values)
            else:
                entry = OvertimeEntry.create(values)
                rec.overtime_entry_id = entry.id