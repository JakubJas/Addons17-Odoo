from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    vacation_weekday_ids = fields.Many2many(
        comodel_name="hr.vacation.weekday",
        relation="hr_employee_vacation_weekday_rel",
        column1="employee_id",
        column2="weekday_id",
        string="Días que descuentan vacaciones",
        help=(
            "Días de la semana que deben descontarse del saldo "
            "de vacaciones para este empleado. "
            "Si no se selecciona ningún día, se utilizará "
            "el comportamiento estándar de Odoo."
        ),
    )

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

        # IMPORTANTE: primero asignamos estas variables
        new_mode = self.overtime_new_mode
        change_date = self.overtime_change_date

        Period = self.env["hr.employee.overtime.period"]

        previous_day = change_date - timedelta(days=1)

        previous_mode = self._get_overtime_mode_for_date(
            previous_day
        )

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
            if change_date <= last_period.date_from:
                raise UserError(
                    "La fecha del nuevo cambio debe ser posterior "
                    "al inicio del último periodo registrado."
                )

            last_period.write({
                "date_to": change_date - timedelta(days=1),
            })
            
        weekly_expected_hours = 0.0

        if new_mode == "weekly":

            if not self.resource_calendar_id:
                raise UserError(
                    "El empleado no tiene un horario de trabajo configurado."
                )

            weekly_expected_hours = self._get_calendar_weekly_hours()

            if weekly_expected_hours <= 0:
                raise UserError(
                    "El horario de trabajo del empleado no tiene "
                    "horas semanales configuradas."
                )

        Period.create({
            "employee_id": self.id,
            "date_from": change_date,
            "date_to": False,
            "calculation_mode": new_mode,
            "weekly_expected_hours": (
                weekly_expected_hours
                if new_mode == "weekly"
                else 0.0
            ),
        })

        self.overtime_new_mode = False
        self.overtime_change_date = False

        today = fields.Date.context_today(self)

        if change_date <= today:
            self.env[
                "hr.attendance"
            ]._rebuild_employee_overtime_from_date(
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
        
    def _get_calendar_weekly_hours(self):
        """
        Obtiene las horas semanales teóricas configuradas
        en el resource.calendar del empleado.

        No tiene en cuenta vacaciones, festivos ni ausencias.
        Solo utiliza la estructura habitual del horario laboral.

        Este valor se utiliza para congelar las horas previstas
        dentro de un periodo semanal flexible.
        """
        self.ensure_one()

        calendar = self.resource_calendar_id

        if not calendar:
            return 0.0

        weekly_hours = 0.0

        for attendance in calendar.attendance_ids:
            hour_from = attendance.hour_from or 0.0
            hour_to = attendance.hour_to or 0.0

            if hour_to > hour_from:
                weekly_hours += hour_to - hour_from

        # Calendarios alternos de dos semanas:
        # attendance_ids contiene las líneas de ambas semanas,
        # así que calculamos la media semanal.
        if (
            "two_weeks_calendar" in calendar._fields
            and calendar.two_weeks_calendar
        ):
            weekly_hours /= 2.0

        return round(weekly_hours, 4)

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
