{
    'name': 'Customer and Vendor Sequence Number',
    'version': '17.0.1.0.0',
    'summary': 'Número de secuencia de clientes y proveedores',
    'description': """
        Este módulo genera los números secuenciales de clientes y proveedores
    """,
    'author': 'Servi Byte Canarias SL',
    'website': 'https://www.servibyte.com',
    'category': 'Tools',
    'license': 'LGPL-3',
    'depends': ['base', 'sale_management', 'purchase'], 
    'data': [
        'data/sequence.xml',
        'views/res_partner.xml',
    ],
    'installable': True,
    'application': False,
    "auto_install": False,
}
