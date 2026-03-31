{
    "name": "Overtime Bank Pro",
    "version": "17.0.1.0",
    "depends": [
        "hr",
        "hr_attendance",
        "hr_holidays",
        "hr_holidays_attendance",
        "mail"
    ],
    'author': 'Servi Byte Canarias SL',
    'website': 'https://www.servibyte.com',
    "category": "Human Resources",
    "summary": "Overtime bank and compensation system",
    "description": "Overtime bank and compensation system",
    "data": [
        'security/security.xml',
        "security/ir.model.access.csv",
        "views/overtime_report_wizard_views.xml",
        "views/overtime_entry_views.xml",
        'views/hide_menus.xml',
        "views/overtime_employee_views.xml",
        "views/overtime_payment_views.xml",
        "views/hr_attendance_inherit.xml",
        "views/overtime_menu.xml",
        "data/cron_alerts.xml"
    ],
    'post_init_hook': 'migrate_overtime_from_attendance',
    "installable": True,
    "application": True
}