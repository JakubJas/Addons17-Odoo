from odoo import fields, models


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
            "Tipos de ausencia a los que se aplicará el cálculo "
            "personalizado de días de vacaciones."
        ),
    )