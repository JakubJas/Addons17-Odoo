from datetime import timedelta

from odoo import models


class HrLeave(models.Model):
    _inherit = "hr.leave"

    def _use_custom_vacation_weekdays(self):
        self.ensure_one()

        if not self.employee_id:
            return False

        if not self.holiday_status_id:
            return False

        if not self.employee_id.vacation_weekday_ids:
            return False

        config = self.env.ref(
            "sb_hr_overtime_bank_pro.vacation_config_default",
            raise_if_not_found=False,
        )

        if not config:
            return False

        if self.holiday_status_id not in config.leave_type_ids:
            return False

        return True

    def _get_custom_vacation_days(self):
        self.ensure_one()

        if not self.request_date_from or not self.request_date_to:
            return 0.0

        weekday_codes = {
            int(code)
            for code in self.employee_id.vacation_weekday_ids.mapped("code")
            if code is not False
        }

        if not weekday_codes:
            return 0.0

        current_date = self.request_date_from
        end_date = self.request_date_to

        total_days = 0

        while current_date <= end_date:
            if current_date.weekday() in weekday_codes:
                total_days += 1

            current_date += timedelta(days=1)

        return float(total_days)

    def _get_duration(
        self,
        check_leave_type=True,
        resource_calendar=None,
    ):

        standard_days, standard_hours = super()._get_duration(
            check_leave_type=check_leave_type,
            resource_calendar=resource_calendar,
        )

        if not self._use_custom_vacation_weekdays():
            return standard_days, standard_hours

        custom_days = self._get_custom_vacation_days()

        return custom_days, standard_hours