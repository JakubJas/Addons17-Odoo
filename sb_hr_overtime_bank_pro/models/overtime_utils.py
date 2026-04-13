from datetime import datetime, time
import pytz

def get_expected_hours(env, employee, date):
    calendar = employee.resource_calendar_id
    if not calendar:
        return 0

    tz = pytz.timezone(employee.tz or 'UTC')

    start = tz.localize(datetime.combine(date, time.min))
    end = tz.localize(datetime.combine(date, time.max))

    intervals = calendar._work_intervals_batch(start, end)

    hours = 0
    for interval in intervals.get(employee.resource_id.id, []):
        hours += (interval[1] - interval[0]).total_seconds() / 3600

    return hours