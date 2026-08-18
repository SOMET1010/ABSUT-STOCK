{
    'name': "ANSUT — Distribution et retraits",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Distribution aux bénéficiaires, QR et PIN de retrait (DSD §19 à §29)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['ansut_equipment'],
    'data': [
        'security/ir.model.access.csv',
        'views/ansut_distribution_views.xml',
    ],
    'installable': True,
    'application': False,
}
