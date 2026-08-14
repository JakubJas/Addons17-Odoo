from datetime import timedelta

from odoo import models, fields, api
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_entry_ids = fields.One2many(
        "hr.overtime.entry",
        "employee_id",
        string="Movimientos Overtime",
    )

    overtime_period_ids = fields.One2many(
        "hr.employee.overtime.period",
        "employee_id",
        string="Historial de modalidades Overtime",
    )

    overtime_balance = fields.Float(
        compute="_compute_overtime_balance",
        string="Overtime Balance"
    )

    overtime_calculation_mode = fields.Selection(
        [
            ("daily", "Diario"),
            ("weekly", "Semanal flexible"),
        ],
        string="Cálculo horas extra",
        default="daily",
        required=True,
    )

    overtime_weekly_from = fields.Date(
        string="Horario flexible desde",
        help=(
            "Fecha a partir de la cual el banco de horas se calcula "
            "semanalmente. Las fechas anteriores mantienen el cálculo diario."
        ),
    )
    
    overtime_current_mode = fields.Selection(
        [
            ("daily", "Diario"),
            ("weekly", "Semanal flexible"),
        ],
        string="Modalidad actual",
        compute="_compute_overtime_current_mode",
        store=False,
    )

    overtime_new_mode = fields.Selection(
        [
            ("daily", "Diario"),
            ("weekly", "Semanal flexible"),
        ],
        string="Nueva modalidad",
    )

    overtime_change_date = fields.Date(
        string="Aplicar desde",
    )

    @api.depends("overtime_entry_ids.hours", "overtime_entry_ids.type", "overtime_entry_ids.state")
    def _compute_overtime_balance(self):
        for emp in self:
            emp.overtime_balance = sum(entry._get_signed_hours() for entry in emp.overtime_entry_ids)

    @api.depends(
        "overtime_period_ids.date_from",
        "overtime_period_ids.date_to",
        "overtime_period_ids.calculation_mode",
        "overtime_calculation_mode",
        "overtime_weekly_from",
    )
    def _compute_overtime_current_mode(self):
        today = fields.Date.context_today(self)

        for emp in self:
            mode = emp._get_overtime_mode_for_date(today)
            # El histórico ("historical") no es una modalidad seleccionable;
            # a efectos de visualización lo tratamos como la base configurada.
            emp.overtime_current_mode = (
                mode if mode in ("daily", "weekly") else "daily"
            )

    def _get_overtime_mode_for_date(self, day):
        self.ensure_one()

        if not day:
            return "daily"

        period = self.env[
            "hr.employee.overtime.period"
        ].search([
            ("employee_id", "=", self.id),
            ("date_from", "<=", day),
            "|",
            ("date_to", "=", False),
            ("date_to", ">=", day),
        ], order="date_from desc", limit=1)

        if period:
            return period.calculation_mode

        # Si no existe ningún periodo específico,
        # mantenemos el comportamiento diario.
        return "daily"

    def action_apply_overtime_mode_change(self):
        self.ensure_one()

        if not self.overtime_new_mode:
            raise UserError(
                "Debes seleccionar la nueva modalidad."
            )

        if not self.overtime_change_date:
            raise UserError(
                "Debes indicar desde qué fecha se aplicará el cambio."
            )

        new_mode = self.overtime_new_mode
        change_date = self.overtime_change_date

        Period = self.env["hr.employee.overtime.period"]

        previous_day = change_date - timedelta(days=1)

        previous_mode = self._get_overtime_mode_for_date(
            previous_day
        )

        # Si ya tenía esa misma modalidad, NO hacemos rebuild
        # ni creamos un periodo innecesario.
        if previous_mode == new_mode:
            raise UserError(
                "El empleado ya tenía esta modalidad antes de "
                "la fecha indicada.\n\n"
                "No es necesario volver a aplicar el mismo tipo "
                "de horario."
            )

        last_period = Period.search([
            ("employee_id", "=", self.id),
        ], order="date_from desc, id desc", limit=1)

        if last_period and not last_period.date_to:
            # Evitamos cerrar un periodo con una fecha inválida
            if change_date <= last_period.date_from:
                raise UserError(
                    "La fecha del nuevo cambio debe ser posterior "
                    "al inicio del último periodo registrado."
                )

            last_period.write({
                "date_to": change_date - timedelta(days=1),
            })

        Period.create({
            "employee_id": self.id,
            "date_from": change_date,
            "date_to": False,
            "calculation_mode": new_mode,
        })

        self.overtime_new_mode = False
        self.overtime_change_date = False

        today = fields.Date.context_today(self)

        if change_date <= today:
            self.env["hr.attendance"]._rebuild_employee_overtime_from_date(
                self,
                change_date,
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Modalidad actualizada",
                "message": (
                    f"La modalidad se aplicará desde "
                    f"{change_date.strftime('%d/%m/%Y')}."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    def action_rebuild_overtime_history(self):
        for employee in self:
            self.env["hr.attendance"]._rebuild_overtime_history_for_employee(
                employee
            )

        return True

    def action_open_overtime_bank(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Overtime Bank",
            "res_model": "hr.overtime.entry",
            "view_mode": "tree,form",
            "domain": [("employee_id", "=", self.id)],
            "context": {
                "default_employee_id": self.id,
            },
        }
