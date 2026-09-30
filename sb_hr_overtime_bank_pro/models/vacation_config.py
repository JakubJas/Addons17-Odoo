from odoo import api, fields, models
from odoo.exceptions import ValidationError


class HrVacationConfig(models.Model):
    _name = "hr.vacation.config"
    _description = "Configuración personalizada de vacaciones"

    name = fields.Char(
        string="Nombre",
        default="Configuración vacaciones",
        required=True,
    )

    leave_type_ids = fields.Many2many(
        comodel_name="hr.leave.type",
        relation="hr_vacation_config_leave_type_rel",
        column1="config_id",
        column2="leave_type_id",
        string="Tipos de ausencia",
        help=(
            "Tipos de ausencia que utilizan la selección "
            "personalizada de días de vacaciones."
        ),
    )

    compensation_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Tipo para descanso por horas extra",
        help=(
            "Tipo de ausencia utilizado cuando un empleado "
            "disfruta horas del Overtime Bank como descanso. "
            "No debe requerir asignación ni utilizar la "
            "deducción nativa de horas extra de Odoo."
        ),
    )

    @api.constrains("compensation_leave_type_id")
    def _check_compensation_leave_type(self):
        for rec in self:

            leave_type = (
                rec.compensation_leave_type_id
            )

            if not leave_type:
                continue

            if (
                "requires_allocation"
                in leave_type._fields
                and leave_type.requires_allocation
                == "yes"
            ):
                raise ValidationError(
                    "El tipo para descanso por horas extra "
                    "no puede requerir una asignación previa."
                )

            if (
                "overtime_deductible"
                in leave_type._fields
                and leave_type.overtime_deductible
            ):
                raise ValidationError(
                    "El tipo para descanso por horas extra "
                    "no puede tener activada la deducción "
                    "nativa de horas extra de Odoo, porque "
                    "el saldo ya lo gestiona Overtime Bank."
                )