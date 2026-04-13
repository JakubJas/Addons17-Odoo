from . import models
from . import wizard

from odoo import fields

def migrate_overtime_from_attendance(env):

    Overtime = env['hr.overtime.entry']

    attendances = env['hr.attendance'].search([
        ('worked_hours', '>', 0),
    ])

    for att in attendances:
        overtime_hours = att.worked_hours - (att.employee_id.resource_calendar_id.hours_per_day or 8)

        if overtime_hours > 0:
            Overtime.with_context(
                skip_overtime_limit=True,
                skip_comp_sync=True
            ).create({
                'employee_id': att.employee_id.id,
                'date': att.check_in.date(),
                'hours': overtime_hours,
                'type': 'extra',
                'state': 'done',
                'attendance_id': att.id,
                'reference': 'Migración inicial',
            })