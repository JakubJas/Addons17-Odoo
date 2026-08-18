from odoo import fields, models


class HrVacationLeaveType(models.Model):
    _name = "hr.vacation.leave.type"
    _description = "Tipo de ausencia para vacaciones personalizadas"

    leave_type_id = fields.Many2one(
        "hr.leave.type",
        string="Tipo de ausencia",
        required=True,
        ondelete="cascade",
    )

    _sql_constraints = [
        (
            "leave_type_unique",
            "unique(leave_type_id)",
            "Este tipo de ausencia ya está configurado.",
        ),
    ]