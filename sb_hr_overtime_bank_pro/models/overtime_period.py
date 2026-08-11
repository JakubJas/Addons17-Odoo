from datetime import date

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrEmployeeOvertimePeriod(models.Model):
    _name = "hr.employee.overtime.period"
    _description = "Periodo de cálculo Overtime del empleado"
    _order = "date_from desc, id desc"

    employee_id = fields.Many2one(
        "hr.employee",
        string="Empleado",
        required=True,
        ondelete="cascade",
        index=True,
    )

    date_from = fields.Date(
        string="Desde",
        required=True,
        index=True,
    )

    date_to = fields.Date(
        string="Hasta",
        index=True,
    )

    calculation_mode = fields.Selection(
        [
            ("daily", "Diario"),
            ("weekly", "Semanal flexible"),
        ],
        string="Modalidad",
        required=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for rec in self:
            if (
                rec.date_from
                and rec.date_to
                and rec.date_to < rec.date_from
            ):
                raise ValidationError(
                    "La fecha 'Hasta' no puede ser anterior "
                    "a la fecha 'Desde'."
                )

    @api.constrains(
        "employee_id",
        "date_from",
        "date_to",
    )
    def _check_overlapping_periods(self):
        for rec in self:
            if not rec.employee_id or not rec.date_from:
                continue

            period_end = rec.date_to or date.max

            overlap = self.search([
                ("id", "!=", rec.id),
                ("employee_id", "=", rec.employee_id.id),
                ("date_from", "<=", period_end),
                "|",
                ("date_to", "=", False),
                ("date_to", ">=", rec.date_from),
            ], limit=1)

            if overlap:
                raise ValidationError(
                    "Este periodo se solapa con otro periodo "
                    "de cálculo del empleado."
                )

    @api.constrains("calculation_mode", "date_from")
    def _check_weekly_starts_on_monday(self):
        for rec in self:
            if (
                rec.calculation_mode == "weekly"
                and rec.date_from
                and rec.date_from.weekday() != 0
            ):
                raise ValidationError(
                    "Los periodos semanales flexibles deben "
                    "comenzar un lunes."
                )