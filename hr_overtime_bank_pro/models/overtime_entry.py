from odoo import models, fields, api


class HrOvertimeEntry(models.Model):
    _name = "hr.overtime.entry"
    _description = "Overtime Bank Entry"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    employee_id = fields.Many2one("hr.employee", required=True)
    date = fields.Date(default=fields.Date.today, tracking=True)
    hours = fields.Float(tracking=True)

    type = fields.Selection([
        ("extra", "Generar banco de horas extras"),
        ("payment", "Pagar horas extras"),
        ("compensation", "Compensar horas extras"),
        ("adjustment", "Ajuste manual")
    ], required=True)

    attendance_id = fields.Many2one("hr.attendance", tracking=True)
    reference = fields.Char(tracking=True)

    state = fields.Selection([
        ("draft", "Draft"),
        ("done", "Confirmed")
    ], default="draft", tracking=True)

    description = fields.Char("Descripción", tracking=True)

    attachment = fields.Binary("Documento")
    attachment_filename = fields.Char("Nombre del archivo", tracking=True)

    leave_allocation_id = fields.Many2one("hr.leave.allocation")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        for rec in records:
            type_label = dict(rec._fields['type'].selection).get(rec.type)

            rec.employee_id.message_post(
                body=f"Registro creado: {rec.hours} horas ({type_label})",
                subtype_xmlid="mail.mt_note"
            )

        if not self.env.context.get("skip_comp_sync"):
            records._sync_compensation_allocation()

        return records

    def write(self, vals):
        old_values = {}

        for rec in self:
            old_values[rec.id] = {
                'hours': rec.hours,
                'type': rec.type,
                'state': rec.state,
            }

        res = super().write(vals)

        for rec in self:
            changes = []

            old = old_values.get(rec.id)

            if 'hours' in vals:
                changes.append(f"Horas: {old['hours']} → {rec.hours}")

            if 'type' in vals:
                old_type = dict(self._fields['type'].selection).get(old['type'])
                new_type = dict(self._fields['type'].selection).get(rec.type)
                changes.append(f"Tipo: {old_type} → {new_type}")

            if 'state' in vals:
                changes.append(f"Estado: {old['state']} → {rec.state}")

            if changes:
                rec.employee_id.message_post(
                    body="Actualización overtime:" .join(changes)
                )

        if not self.env.context.get("skip_comp_sync") and any(
            field in vals for field in ["hours", "employee_id", "type", "state", "date"]
        ):
            self._sync_compensation_allocation()

        return res

    def action_confirm(self):
        self.with_context(skip_comp_sync=True).write({"state": "done"})
        self._sync_compensation_allocation()

        for rec in self:
            rec.message_post(
                body=f"Registro confirmado: {rec.hours} horas ({rec.type})"
            )

    def action_set_to_draft(self):
        self.with_context(skip_comp_sync=True).write({"state": "draft"})
        self._sync_compensation_allocation()

    def _get_default_compensation_leave_type(self):
        leave_type_model = self.env["hr.leave.type"]

        domain = []
        if "requires_allocation" in leave_type_model._fields:
            domain = [("requires_allocation", "=", "yes")]
        elif "allocation_type" in leave_type_model._fields:
            domain = [("allocation_type", "!=", "no")]

        leave_type = leave_type_model.search(domain, order="id", limit=1) if domain else leave_type_model.search([], order="id", limit=1)
        return leave_type

    def _prepare_allocation_values(self, leave_type, days, hours):
        self.ensure_one()
        values = {
            "name": f"Compensación horas extras {self.employee_id.name or ''} ({hours:.2f}h)",
            "employee_id": self.employee_id.id,
            "holiday_status_id": leave_type.id,
        }

        allocation_model = self.env["hr.leave.allocation"]
        if "number_of_days" in allocation_model._fields:
            values["number_of_days"] = days
        if "number_of_days_display" in allocation_model._fields:
            values["number_of_days_display"] = days
        if "number_of_hours_display" in allocation_model._fields:
            values["number_of_hours_display"] = hours
        if "holiday_type" in allocation_model._fields:
            values["holiday_type"] = "employee"
        return values

    def _validate_allocation(self, allocation):
        if hasattr(allocation, "_action_validate"):
            allocation._action_validate()
            return

        if hasattr(allocation, "action_confirm") and allocation.state == "draft":
            allocation.action_confirm()

        if hasattr(allocation, "action_validate"):
            try:
                allocation.action_validate()
            except TypeError:
                if "state" in allocation._fields:
                    allocation.write({"state": "validate"})
            return

        if "state" in allocation._fields:
            allocation.write({"state": "validate"})

    def _sync_compensation_allocation(self):
        Allocation = self.env["hr.leave.allocation"].sudo()

        for rec in self:
            allocation = rec.leave_allocation_id.sudo()
            needs_allocation = (
                rec.type == "compensation"
                and rec.state == "done"
                and abs(rec.hours or 0.0) > 0.0
                and rec.employee_id
            )

            if not needs_allocation:
                if allocation:
                    rec.with_context(skip_comp_sync=True).write({"leave_allocation_id": False})
                    allocation.unlink()
                continue

            leave_type = rec._get_default_compensation_leave_type()
            if not leave_type:
                continue

            hours = abs(rec.hours or 0.0)
            hours_per_day = rec.employee_id.resource_calendar_id.hours_per_day or 8.0
            days = hours / hours_per_day
            values = rec._prepare_allocation_values(leave_type, days, hours)

            if allocation:
                allocation.write(values)
            else:
                allocation = Allocation.create(values)
                rec.with_context(skip_comp_sync=True).write({
                    "leave_allocation_id": allocation.id,
                })

            rec._validate_allocation(allocation)

    def _get_signed_hours(self):
        self.ensure_one()

        if self.state != "done":
            return 0.0

        if self.type == "extra":
            return self.hours

        if self.type in ("payment", "compensation"):
            return -abs(self.hours)

        if self.type == "adjustment":
            return self.hours

        return 0.0

    def unlink(self):
        for rec in self:
            type_label = dict(self._fields['type'].selection).get(rec.type)

            # Log ANTES de borrar
            rec.employee_id.message_post(
                body=f"Overtime eliminado: {rec.hours}h ({type_label})"
            )

            allocation = rec.leave_allocation_id.sudo()
            if allocation:
                rec.with_context(skip_comp_sync=True).write({"leave_allocation_id": False})
                allocation.unlink()

        return super().unlink()
