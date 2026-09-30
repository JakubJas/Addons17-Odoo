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

    # =========================================================
    # VACACIONES
    #
    # Los tipos incluidos aquí utilizarán la configuración
    # L-M-X-J-V-S-D de cada empleado.
    # =========================================================

    leave_type_ids = fields.Many2many(
        comodel_name="hr.leave.type",
        relation="hr_vacation_config_leave_type_rel",
        column1="config_id",
        column2="leave_type_id",
        string="Tipos de vacaciones afectados",
        help=(
            "Tipos de ausencia que utilizarán la selección "
            "personalizada de días computables del empleado "
            "(L-M-X-J-V-S-D)."
        ),
    )

    # =========================================================
    # DESCANSO POR HORAS EXTRA
    # =========================================================

    compensation_leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Tipo para descanso por horas extra",
        help=(
            "Tipo de ausencia que Overtime utilizará cuando "
            "un empleado disfrute horas del banco como descanso. "
            "No debe requerir asignación ni utilizar la deducción "
            "nativa de horas extra de Odoo."
        ),
    )

    # =========================================================
    # VALIDACIÓN
    # =========================================================

    @api.constrains(
        "leave_type_ids",
        "compensation_leave_type_id",
    )
    def _check_leave_type_configuration(self):

        for rec in self:

            leave_type = (
                rec.compensation_leave_type_id
            )

            if not leave_type:
                continue

            # -------------------------------------------------
            # No mezclar vacaciones y descanso Overtime
            # -------------------------------------------------

            if leave_type in rec.leave_type_ids:
                raise ValidationError(
                    "El tipo utilizado para descanso por "
                    "horas extra no puede estar también "
                    "dentro de los tipos de vacaciones "
                    "afectados."
                )

            # -------------------------------------------------
            # No debe requerir asignación
            # -------------------------------------------------

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

            # -------------------------------------------------
            # No usar el banco nativo de Odoo
            # -------------------------------------------------

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