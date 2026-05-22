{
    'name': 'ServiLOPD',
    'version': '17.0.1.0.0',
    'depends': [
        'base', 
        'contacts', 
        'mail',
        'website'
        ],
    'author': 'Servi Byte Canarias SL',
    'website': 'https://www.servibyte.com',
    "category": "Sales",
    'summary': 'Gestión básica LOPD para clientes y proveedores',
    "description": "Gestión básica LOPD para clientes y proveedores",
    'data': [
        'security/ir.model.access.csv',
        'views/res_partner_views.xml',
        'views/servilopd_request_views.xml',
        'views/servilopd_document_views.xml',
        'views/servilopd_menu.xml',
        'views/servilopd_templates.xml',
        'views/login_templates.xml',
        'data/mail_template.xml',
        'data/ir_cron.xml',
        'data/server_action.xml',
        'reports/lopd_contract_report.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'sb_sales_servi_lopd/static/src/css/login_clean.css',
        ],
    },
    'installable': True,
    'application': True,
}