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
    
    check_in = fields.Datetime(
        string="Entrada",
        tracking=True,
    )

    check_out = fields.Datetime(
        string="Salida",
        tracking=True,
    )

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
    
    expected_hours = fields.Float(
        string="Horas previstas",
        tracking=True,
        help="Horas que el empleado debía trabajar en el periodo calculado.",
    )

    worked_hours = fields.Float(
        string="Horas trabajadas",
        tracking=True,
        help="Horas realmente trabajadas por el empleado en el periodo calculado.",
    )

    difference_hours = fields.Float(
        string="Diferencia de horas",
        compute="_compute_difference_hours",
        store=True,
        readonly=True,
        tracking=True,
        help="Diferencia entre las horas trabajadas y las horas previstas.",
    )

    def _get_total_balance(self, employee):
        entries = self.search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'done')
        ])
        return sum(rec._get_signed_hours() for rec in entries)
    
    @api.depends("expected_hours", "worked_hours")
    def _compute_difference_hours(self):
        for rec in self:
            rec.difference_hours = (
                (rec.worked_hours or 0.0)
                - (rec.expected_hours or 0.0)
            )

    @api.model_create_multi
    def create(self, vals_list):
        # Se utiliza en reconstrucciones y sincronizaciones automáticas.
        if self.env.context.get("skip_overtime_limit"):
            records = super().create(vals_list)

            if not self.env.context.get("skip_comp_sync"):
                records._sync_compensation_allocation()

            return records

        for vals in vals_list:
            new_state = vals.get("state", "draft")

            # Los registros en borrador todavía no afectan al saldo.
            if new_state != "done":
                continue

            employee_id = vals.get("employee_id")
            if not employee_id:
                continue

            employee = self.env["hr.employee"].browse(
                employee_id
            ).exists()

            if not employee:
                continue

            simulated_entry = self.new(vals)

            current_balance = self._get_total_balance(employee)
            added_hours = simulated_entry._get_signed_hours()
            future_balance = current_balance + added_hours

            if future_balance > self.MAX_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} horas acumuladas.\n\n"
                    f"Este movimiento modificaría el saldo en "
                    f"{round(added_hours, 2)} horas.\n\n"
                    f"El saldo final sería "
                    f"{round(future_balance, 2)} horas.\n\n"
                    f"No puede superar el límite de "
                    f"{self.MAX_HOURS} horas."
                )

            if future_balance < self.MIN_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} horas acumuladas.\n\n"
                    f"Este movimiento modificaría el saldo en "
                    f"{round(added_hours, 2)} horas.\n\n"
                    f"El saldo final sería "
                    f"{round(future_balance, 2)} horas.\n\n"
                    f"No puede bajar del límite de "
                    f"{self.MIN_HOURS} horas."
                )

        records = super().create(vals_list)

        type_labels = dict(
            self.env["hr.overtime.entry"]._fields["type"].selection
        )

        for rec in records:
            type_label = type_labels.get(rec.type, rec.type)

            rec.employee_id.message_post(
                body=(
                    f"Registro creado: "
                    f"{rec.hours} horas ({type_label})"
                ),
                subtype_xmlid="mail.mt_note",
            )

        if not self.env.context.get("skip_comp_sync"):
            records._sync_compensation_allocation()

        return records

    def write(self, vals):
        if self.env.context.get("skip_overtime_limit"):
            return super().write(vals)

        old_values = {}

        for rec in self:
            old_values[rec.id] = {
                "employee_id": rec.employee_id,
                "hours": rec.hours,
                "type": rec.type,
                "state": rec.state,
            }

        for rec in self:
            new_employee = self.env["hr.employee"].browse(
                vals.get("employee_id", rec.employee_id.id)
            ).exists()

            new_hours = vals.get("hours", rec.hours)
            new_type = vals.get("type", rec.type)
            new_state = vals.get("state", rec.state)

            if not new_employee or new_state != "done":
                continue

            simulated_entry = self.new({
                "employee_id": new_employee.id,
                "hours": new_hours,
                "type": new_type,
                "state": new_state,
            })

            new_signed_hours = simulated_entry._get_signed_hours()

            current_balance = self._get_total_balance(new_employee)

            # Si el registro ya estaba confirmado para ese mismo empleado,
            # quitamos primero su efecto anterior.
            previous_effect = 0.0

            if (
                rec.state == "done"
                and rec.employee_id == new_employee
            ):
                previous_effect = rec._get_signed_hours()

            future_balance = (
                current_balance
                - previous_effect
                + new_signed_hours
            )

            if future_balance > self.MAX_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} horas acumuladas.\n\n"
                    f"El nuevo saldo sería "
                    f"{round(future_balance, 2)} horas.\n\n"
                    f"No puede superar el límite de "
                    f"{self.MAX_HOURS} horas."
                )

            if future_balance < self.MIN_HOURS:
                raise UserError(
                    f"El empleado tiene actualmente "
                    f"{round(current_balance, 2)} horas acumuladas.\n\n"
                    f"El nuevo saldo sería "
                    f"{round(future_balance, 2)} horas.\n\n"
                    f"No puede bajar del límite de "
                    f"{self.MIN_HOURS} horas."
                )

        result = super().write(vals)

        type_labels = dict(
            self.env["hr.overtime.entry"]._fields["type"].selection
        )

        for rec in self:
            old = old_values.get(rec.id, {})
            changes = []

            if "hours" in vals:
                changes.append(
                    f"Horas: {old.get('hours', 0.0)} → {rec.hours}"
                )

            if "type" in vals:
                old_type = type_labels.get(
                    old.get("type"),
                    old.get("type"),
                )
                new_type = type_labels.get(rec.type, rec.type)

                changes.append(
                    f"Tipo: {old_type} → {new_type}"
                )

            if "state" in vals:
                changes.append(
                    f"Estado: "
                    f"{old.get('state', '')} → {rec.state}"
                )

            if changes:
                rec.employee_id.message_post(
                    body=(
                        "Actualización overtime: "
                        + " | ".join(changes)
                    ),
                    subtype_xmlid="mail.mt_note",
                )

        if (
            not self.env.context.get("skip_comp_sync")
            and any(
                field_name in vals
                for field_name in [
                    "hours",
                    "employee_id",
                    "type",
                    "state",
                    "date",
                ]
            )
        ):
            self._sync_compensation_allocation()

        return result

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
