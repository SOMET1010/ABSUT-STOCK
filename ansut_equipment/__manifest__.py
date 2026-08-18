{
    'name': "ANSUT — Référentiel équipements",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Traçabilité unitaire des équipements ANSUT (DSD §11 à §14, §33)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/stock_lot_views.xml',
    ],
    'installable': True,
    'application': False,
}
