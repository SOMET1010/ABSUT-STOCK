{
    'name': "ANSUT — Jeu d'essai",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Données de démonstration pour éprouver le parcours de bout en bout",
    'description': """
Installe un parc, des bénéficiaires et un retrait prêt à être servi, pour
pouvoir suivre le parcours complet sans rien saisir au préalable.

À NE PAS INSTALLER EN PRODUCTION : ce module écrit un PIN connu (123456) sur
les retraits de démonstration, afin qu'un testeur puisse aller au bout du
parcours agent.
""",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['ansut_withdrawal'],
    'data': [
        'data/ansut_demo_data.xml',
    ],
    'installable': True,
    'application': False,
}
