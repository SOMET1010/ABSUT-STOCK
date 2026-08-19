{
    'name': "ANSUT — SAV et échange standard",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Garantie, réparation et échange standard adossés à Helpdesk (DSD §30 à §34)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    # helpdesk_stock apporte déjà le numéro de série et les retours sur le
    # ticket, helpdesk_repair le lien vers les ordres de réparation : ce module
    # ne réécrit ni l'un ni l'autre.
    'depends': ['ansut_distribution', 'helpdesk_stock', 'helpdesk_repair'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/ansut_exchange_wizard_views.xml',
        'views/helpdesk_ticket_views.xml',
        'views/repair_order_views.xml',
    ],
    'installable': True,
    'application': False,
}
