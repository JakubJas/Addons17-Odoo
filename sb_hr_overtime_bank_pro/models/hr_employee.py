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

    def _get_overtime_mode_for_date(self, date):
        """Modalidad de cálculo (diario/semanal) vigente para `date`.

        Prioriza el histórico de periodos (`overtime_period_ids`). Si no hay
        ningún periodo que cubra esa fecha, se conserva el comportamiento
        heredado de `overtime_calculation_mode` / `overtime_weekly_from`
        para no alterar el cálculo de datos anteriores a la primera vez que
        se use el nuevo flujo de cambio de modalidad. Puede devolver
        "historical" cuando la fecha es anterior al inicio del modo semanal
        heredado, en cuyo caso el llamador debe reconstruir a partir de las
        horas extra registradas directamente en Asistencias.
        """
        self.ensure_one()

        period = self.overtime_period_ids.filtered(
            lambda p: p.date_from <= date and (not p.date_to or p.date_to >= date)
        )[:1]

        if period:
            return period.calculation_mode

        if self.overtime_calculation_mode == "weekly" and self.overtime_weekly_from:
            if date >= self.overtime_weekly_from:
                return "weekly"
            return "historical"

        return self.overtime_calculation_mode or "daily"

    def action_apply_overtime_mode_change(self):
        self.ensure_one()

        if not self.overtime_new_mode or not self.overtime_change_date:
            raise UserError(
                "Selecciona la nueva modalidad y la fecha desde la que "
                "aplicarla."
            )

        if (
            self.overtime_new_mode == "weekly"
            and self.overtime_change_date.weekday() != 0
        ):
            raise UserError(
                "Los periodos semanales flexibles deben comenzar un lunes."
            )

        open_period = self.overtime_period_ids.filtered(
            lambda p: not p.date_to
        )

        if open_period:
            if self.overtime_change_date <= open_period.date_from:
                open_period.unlink()
            else:
                open_period.write({
                    "date_to": self.overtime_change_date - timedelta(days=1),
                })

        self.env["hr.employee.overtime.period"].create({
            "employee_id": self.id,
            "date_from": self.overtime_change_date,
            "calculation_mode": self.overtime_new_mode,
        })

        change_date = self.overtime_change_date

        self.write({
            "overtime_new_mode": False,
            "overtime_change_date": False,
        })

        self.env["hr.attendance"]._rebuild_employee_overtime_from_date(
            self, change_date
        )

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
