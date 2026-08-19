{
    'name': "ANSUT — Point de retrait",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Écran agent, remise contrôlée et PV de remise (DSD §25 à §29)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['ansut_distribution'],
    'data': [
        'security/ir.model.access.csv',
        'report/ansut_withdrawal_report.xml',
        'report/ansut_withdrawal_report_templates.xml',
        'wizard/ansut_withdrawal_wizard_views.xml',
        'views/ansut_distribution_views.xml',
    ],
    'installable': True,
    'application': False,
}
