from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

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

    overtime_change_date = fields.Date(
        string="Aplicar desde",
    )

    @api.depends("overtime_entry_ids.hours", "overtime_entry_ids.type", "overtime_entry_ids.state")
    def _compute_overtime_balance(self):
        for emp in self:
            emp.overtime_balance = sum(entry._get_signed_hours() for entry in emp.overtime_entry_ids)

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
