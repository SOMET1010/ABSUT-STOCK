{
    'name': "ANSUT — Gestion du parc d'équipements",
    'version': '17.0.1.0.0',
    'category': 'Inventory',
    'summary': "Parc, bénéficiaires, retrait sécurisé par QR et PIN, SAV",
    'description': """
Plateforme de gestion du parc d'équipements ANSUT.

Ce module n'apporte aucun modèle : il installe la chaîne complète en une fois.

Ce qu'il installe
=================

- **ansut_theme** : la charte du Design System (DSD 5 a 8, 62)
- **ansut_equipment** : referentiel equipement, IMEI, marquage, garantie
- **ansut_beneficiary** : beneficiaires, eligibilite, plafonds par categorie
- **ansut_distribution** : le retrait securise, adosse aux transferts Odoo
- **ansut_withdrawal** : l'ecran agent du comptoir et le PV de remise

Modules associes
================

**ansut_sav** (SAV, garantie, echange standard) s'installe de lui-meme si
Helpdesk est present. Il exige Odoo Enterprise et reste donc hors des
dependances, pour que le socle s'installe aussi en communautaire.

**ansut_demo** installe un jeu d'essai avec un PIN connu. Il n'est jamais
installe automatiquement, et ne doit pas l'etre en production.

Principe de conception
======================

Ce qu'Odoo sait deja faire n'est pas refait : un retrait *est* un transfert,
un beneficiaire *est* un contact, un equipement *est* un numero de serie. Seul
ce qui manque au standard a ete construit, au premier rang l'authentification
au comptoir d'un beneficiaire qui n'est pas un utilisateur Odoo.
""",
    'author': 'ANSUT',
    'license': 'LGPL-3',
    'depends': [
        'ansut_theme',
        'ansut_equipment',
        'ansut_beneficiary',
        'ansut_distribution',
        'ansut_withdrawal',
    ],
    'data': [],
    'installable': True,
    'application': True,
}
