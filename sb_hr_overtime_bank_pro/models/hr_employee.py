from odoo import models, fields, api


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    overtime_entry_ids = fields.One2many(
        "hr.overtime.entry",
        "employee_id"
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
        help="Define cómo se calculan automáticamente las horas extra de este empleado.",
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
