from . import models
from . import wizard

from odoo import fields

def migrate_overtime_from_attendance(env):
    
    from .models.overtime_utils import get_expected_hours

    Overtime = env['hr.overtime.entry']
    Attendance = env['hr.attendance']

    attendances = Attendance.search([
        ('check_out', '!=', False),
    ])

    for att in attendances:
        employee = att.employee_id
        date = att.check_in.date()

        expected_hours = _get_expected_hours(employee, date)
        worked_hours = att.worked_hours or 0

        overtime_hours = worked_hours - expected_hours

        # SOLO si hay horas extra reales
        if overtime_hours > 0:
            Overtime.with_context(
                skip_overtime_limit=True,
                skip_comp_sync=True
            ).create({
                'employee_id': employee.id,
                'date': date,
                'hours': overtime_hours,
                'type': 'extra',
                'state': 'done',
                'attendance_id': att.id,
                'reference': 'Migración automática',
            })