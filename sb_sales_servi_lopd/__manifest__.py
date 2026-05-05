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
        'views/servilopd_templates.xml',
    ],
    'installable': True,
    'application': True,
}