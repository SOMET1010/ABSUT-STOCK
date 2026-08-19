{
    'name': "ANSUT — Distribution et retraits",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Retrait sécurisé par QR et PIN, adossé aux transferts Odoo (DSD §19 à §29)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['ansut_equipment', 'ansut_beneficiary'],
    'data': [
        'data/ansut_distribution_data.xml',
        'views/stock_picking_views.xml',
    ],
    'installable': True,
    'application': False,
}
