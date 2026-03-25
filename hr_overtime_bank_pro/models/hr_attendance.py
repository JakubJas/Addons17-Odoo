from odoo import models, fields, api


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    overtime_entry_id = fields.Many2one("hr.overtime.entry")

    @property
    def _overtime_entry_values(self):
        return {
            "reference": "Attendance overtime",
            "type": "extra",
            "state": "done",
        }

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

            if overtime > 0:
                values = {
                    "employee_id": rec.employee_id.id,
                    "date": rec._overtime_source_date,
                    "hours": overtime,
                    "attendance_id": rec.id,
                    **rec._overtime_entry_values,
                }

                if rec.overtime_entry_id:
                    rec.overtime_entry_id.write(values)
                else:
                    entry = OvertimeEntry.create(values)
                    rec.overtime_entry_id = entry.id
            elif rec.overtime_entry_id:
                rec.overtime_entry_id.unlink()
                rec.overtime_entry_id = False
