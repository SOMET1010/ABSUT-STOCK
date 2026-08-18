{
    'name': "ANSUT — Design System",
    'version': '17.0.1.0.0',
    'category': 'Theme/Backend',
    'summary': "Identité visuelle ANSUT : jetons, couleurs, typographie (DSD §5 à §8, §62)",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': ['web'],
    'assets': {
        # Les variables SCSS doivent précéder Bootstrap pour surcharger ses défauts.
        'web._assets_primary_variables': [
            ('prepend', 'ansut_theme/static/src/scss/primary_variables.scss'),
        ],
        'web.assets_backend': [
            'ansut_theme/static/src/scss/tokens.scss',
            'ansut_theme/static/src/scss/backend.scss',
        ],
    },
    'installable': True,
    'application': False,
}
