from odoo import fields, models


class HrVacationWeekday(models.Model):
    _name = "hr.vacation.weekday"
    _description = "Día computable para vacaciones"
    _order = "sequence, id"

    name = fields.Char(
        string="Día",
        required=True,
        readonly=True,
    )

    code = fields.Selection(
        [
            ("0", "Lunes"),
            ("1", "Martes"),
            ("2", "Miércoles"),
            ("3", "Jueves"),
            ("4", "Viernes"),
            ("5", "Sábado"),
            ("6", "Domingo"),
        ],
        string="Código",
        required=True,
        readonly=True,
    )

    sequence = fields.Integer(
        string="Orden",
        default=10,
        readonly=True,
    )

    _sql_constraints = [
        (
            "vacation_weekday_code_unique",
            "unique(code)",
            "Ya existe este día de la semana.",
        ),
    ]