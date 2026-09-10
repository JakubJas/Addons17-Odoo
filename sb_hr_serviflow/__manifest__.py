{
    'name': 'Serviflow',
    'version': '17.0.1.0.3',
    'summary': 'Flujo de trabajo entre departamentos/modulos',
    'description': """
        Este módulo permite gestionar:
        - Flow entre departamentos
    """,
    'author': 'Servi Byte Canarias SL',
    'website': 'https://www.servibyte.com',
    'category': 'Tools',
    'license': 'LGPL-3',
    'depends': ['base','crm','mail', 'sale', 'sale_crm'],
    'data': [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/serviflow_reviewer_config_views.xml",
        "views/serviflow_task_views.xml",
        "views/serviflow_request_budget_wizard_views.xml",
        "views/crm_lead_views.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sb_hr_serviflow/static/src/js/serviflow_activity_menu.js",
            "sb_hr_serviflow/static/src/xml/serviflow_activity_menu.xml",
            "sb_hr_serviflow/static/src/js/crm_serviflow_kanban.js",
        ],
    },
    'installable': True,
    'application': True,
}
