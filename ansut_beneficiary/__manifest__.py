{
    'name': "ANSUT — Bénéficiaires",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Référentiel des bénéficiaires d'équipements (DSD §22)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['ansut_equipment', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'data/ansut_beneficiary_category_data.xml',
        'views/ansut_beneficiary_category_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
}
