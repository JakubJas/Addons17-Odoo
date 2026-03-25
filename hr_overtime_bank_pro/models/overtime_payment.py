from odoo import models, fields, api


class HrOvertimePayment(models.Model):
    _name = "hr.overtime.payment"
    _description = "Overtime Payment"

    employee_id = fields.Many2one("hr.employee", required=True)
    date = fields.Date(default=fields.Date.today)
    hours = fields.Float(required=True)

    state = fields.Selection([
        ("draft", "Borrador"),
        ("done", "Confirmado")
    ], default="draft")

    description = fields.Char("Description")

    attachment = fields.Binary("Document")
    attachment_filename = fields.Char("File name")

    overtime_entry_id = fields.Many2one("hr.overtime.entry")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get("skip_payment_sync"):
            records._sync_payment_entry()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get("skip_payment_sync"):
            self._sync_payment_entry()
        return res

    def action_confirm(self):
        self.with_context(skip_payment_sync=True).write({"state": "done"})
        self._sync_payment_entry()

    def action_set_to_draft(self):
        self.with_context(skip_payment_sync=True).write({"state": "draft"})
        self._sync_payment_entry()

    def _sync_payment_entry(self):
        OvertimeEntry = self.env["hr.overtime.entry"]
        for rec in self:
            entry = rec.overtime_entry_id

            if rec.state != "done":
                if entry:
                    rec.with_context(skip_payment_sync=True).write({"overtime_entry_id": False})
                    entry.unlink()
                continue

            values = {
                "employee_id": rec.employee_id.id,
                "date": rec.date,
                "hours": abs(rec.hours),
                "type": "payment",
                "state": "done",
                "reference": "Payroll payment",
                "description": rec.description,
            }

            if entry:
                entry.write(values)
                continue

            entry = OvertimeEntry.create(values)
            rec.with_context(skip_payment_sync=True).write({"overtime_entry_id": entry.id})
