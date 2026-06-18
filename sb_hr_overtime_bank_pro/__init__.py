from . import models
from . import wizard


def _get_attendance_overtime(att):
    if 'overtime_hours' in att._fields:
        return att.overtime_hours or 0.0
    if 'extra_hours' in att._fields:
        return att.extra_hours or 0.0
    return 0.0


def migrate_overtime_from_attendance(env):
    Overtime = env['hr.overtime.entry']
    Attendance = env['hr.attendance']

    attendances = Attendance.search([
        ('check_out', '!=', False),
    ])

    for att in attendances:
        if not att.employee_id or not att.check_in:
            continue

        overtime_hours = _get_attendance_overtime(att)

        if overtime_hours == 0:
            continue

        entry_type = 'extra' if overtime_hours > 0 else 'compensation'
        hours = abs(overtime_hours)

        existing = Overtime.search([
            '|',
            ('attendance_id', '=', att.id),
            '&',
            ('employee_id', '=', att.employee_id.id),
            ('date', '=', att.check_in.date()),
            ('type', '=', 'extra'),
            ('reference', '=', 'Migración automática desde Asistencias'),
        ], limit=1)

        if existing:
            continue

        Overtime.with_context(
            skip_overtime_limit=True,
            skip_comp_sync=True,
        ).create({
            'employee_id': att.employee_id.id,
            'date': att.check_in.date(),
            'hours': hours,
            'type': entry_type,
            'state': 'done',
            'attendance_id': att.id,
            'reference': 'Migración automática desde Asistencias',
        })