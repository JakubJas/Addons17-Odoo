{
    'name': 'Serviflow',
    'version': '17.0.1.0.0',
    'summary': 'Flujo de trabajo entre departamentos/modulos',
    'description': """
        Este módulo permite gestionar:
        - Flow entre departamentos
    """,
    'author': 'Servi Byte Canarias SL',
    'website': 'https://www.servibyte.com',
    'category': 'Tools',
    'license': 'LGPL-3',
    'depends': ['base','crm','mail'],
    'data': [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/serviflow_reviewer_config_views.xml",
        "views/serviflow_task_views.xml",
    ],
    'installable': True,
    'application': True,
}
