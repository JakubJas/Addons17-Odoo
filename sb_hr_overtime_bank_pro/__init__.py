from . import models
from . import wizard
from . import report

from odoo import fields

def migrate_overtime_from_attendance(env):

    Overtime = env['hr.overtime.entry']
    Attendance = env['hr.attendance']

    attendances = Attendance.search([
        ('check_out', '!=', False),
    ])

    for att in attendances:
        employee = att.employee_id

        if not employee or not employee.resource_calendar_id:
            continue

        hours_per_day = employee.resource_calendar_id.hours_per_day or 8.0
        worked = att.worked_hours or 0.0
        overtime = worked - hours_per_day

        if overtime <= 0:
            continue

        existing = Overtime.search([
            ('attendance_id', '=', att.id)
        ], limit=1)

        if existing:
            continue

        Overtime.create({
            'employee_id': employee.id,
            'date': att.check_in.date() if att.check_in else fields.Date.today(),
            'hours': overtime,
            'type': 'extra',
            'attendance_id': att.id,
            'reference': 'Migración automática desde Asistencias',
            'state': 'done',
        })