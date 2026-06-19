from odoo import models, fields, api
from odoo.exceptions import UserError


class HrOvertimeEntry(models.Model):
    _name = "hr.overtime.entry"
    _description = "Overtime Bank Entry"
    _order = "date desc, id desc"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    MIN_HOURS = -80
    MAX_HOURS = 80

    employee_id = fields.Many2one("hr.employee", required=True)
    date = fields.Date(default=fields.Date.today, tracking=True)
    hours = fields.Float(tracking=True)

    type = fields.Selection([
        ("extra", "Generar banco de horas extras"),
        ("payment", "Pagar horas extras"),
        ("compensation", "Compensar horas extras"),
        ("early_exit", "Salida temprana"),
        ("adjustment", "Ajuste manual")
    ], required=True)

    attendance_id = fields.Many2one("hr.attendance", tracking=True)
    reference = fields.Char(tracking=True)

    state = fields.Selection([
        ("draft", "Borrador"),
        ("done", "Confirmado")
    ], default="draft", tracking=True)

    description = fields.Char("Descripción", tracking=True)

    attachment = fields.Binary("Documento")
    attachment_filename = fields.Char("Nombre del archivo", tracking=True)

    leave_allocation_id = fields.Many2one("hr.leave.allocation")
    
    signed_hours = fields.Float(string="Horas reales", compute="_compute_signed_hours", store=True)

    def _get_total_balance(self, employee):
        entries = self.search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'done')
        ])
        return sum(rec._get_signed_hours() for rec in entries)

    @api.model_create_multi
    def create(self, vals_list):

        # 🔥 SALTAR VALIDACIÓN EN MIGRACIÓN
        if self.env.context.get('skip_overtime_limit'):
            records = super().create(vals_list)

            if not self.env.context.get("skip_comp_sync"):
                records._sync_compensation_allocation()

            return records

        for vals in vals_list:
            if vals.get('type') == 'extra' and vals.get('state', 'draft') == 'done':

                employee = self.env['hr.employee'].browse(vals.get('employee_id'))

                fake = self.new(vals)
                added_hours = fake._get_signed_hours()
                current_balance = self._get_total_balance(employee)
                future_balance = current_balance + added_hours

                if future_balance > self.MAX_HOURS:
                    raise UserError(
                        f"El empleado ya tiene {round(current_balance, 2)} horas acumuladas.\n\n"
                        f"Estás intentando añadir {round(added_hours, 2)} horas.\n\n"
                        f"El saldo final sería {round(future_balance, 2)} horas.\n\n"
                        f"No puede superar el límite de {self.MAX_HOURS} horas.\n\n"
                        f"Reduce las horas o compensa antes de añadir más."
                    )

                if future_balance < self.MIN_HOURS:
                    raise UserError(
                        f"El empleado ya tiene {round(current_balance, 2)} horas acumuladas.\n\n"
                        f"Estás intentando restar {abs(round(added_hours, 2))} horas.\n\n"
                        f"El saldo final sería {round(future_balance, 2)} horas.\n\n"
                        f"No puede bajar de {self.MIN_HOURS} horas.\n\n"
                        f"Revisa la compensación o ajusta las horas."
                    )

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

        # 🔥 SALTAR VALIDACIÓN EN MIGRACIÓN
        if self.env.context.get('skip_overtime_limit'):
            return super().write(vals)

        for rec in self:
            if any(field in vals for field in ['hours', 'type', 'state']):

                new_type = vals.get('type', rec.type)
                new_state = vals.get('state', rec.state)
                new_hours = vals.get('hours', rec.hours)

                if new_type == 'extra' and new_state == 'done':
                    fake = rec.new({
                        'employee_id': rec.employee_id.id,
                        'hours': new_hours,
                        'type': new_type,
                        'state': new_state,
                    })

                    future_balance = self._get_total_balance(rec.employee_id) \
                                     - rec._get_signed_hours() \
                                     + fake._get_signed_hours()

                    if future_balance > self.MAX_HOURS:
                        raise UserError(
                            f"El empleado tiene actualmente {round(self._get_total_balance(rec.employee_id), 2)} horas.\n\n"
                            f"El nuevo saldo sería {round(future_balance, 2)} horas.\n\n"
                            f"No puede superar el límite de {self.MAX_HOURS} horas.\n\n"
                            f"Reduce las horas o compensa antes de añadir más."
                        )

        res = super().write(vals)

        # LOG
        for rec in self:
            rec.employee_id.message_post(
                body=f"Actualización overtime: {rec.hours}h ({rec.type})"
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

        if self.type in ("early_exit", "payment", "compensation"):
            return -abs(self.hours)

        if self.type == "adjustment":
            return self.hours

        return 0.0
    
    @api.depends('hours', 'type', 'state')
    def _compute_signed_hours(self):
        for rec in self:
            rec.signed_hours = rec._get_signed_hours()

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
