# Installer ANSUT Stock

Un seul module à cocher : **ANSUT — Gestion du parc d'équipements**
(`ansut_stock`). Il entraîne toute la chaîne.

## 1. Déposer les modules

Décompressez l'archive dans le dossier d'addons de votre instance, à côté de
vos autres modules :

```bash
unzip ansut-stock-modules.zip -d /chemin/vers/addons/
```

L'archive contient huit dossiers, chacun étant un module Odoo 17 autonome.

## 2. Installer

**Par l'interface** — *Applications* → *Mettre à jour la liste des
applications* → chercher « ANSUT » → **Installer**.

**En ligne de commande :**

```bash
odoo -d votre_base -i ansut_stock --stop-after-init
```

## 3. Ce qui s'installe, et ce qui ne s'installe pas

| Module | Installé par `ansut_stock` |
|---|---|
| `ansut_theme` — charte du Design System | oui |
| `ansut_equipment` — référentiel équipement | oui |
| `ansut_beneficiary` — bénéficiaires et éligibilité | oui |
| `ansut_distribution` — retrait sécurisé QR et PIN | oui |
| `ansut_withdrawal` — écran agent et PV de remise | oui |
| `ansut_sav` — SAV, garantie, échange standard | **seulement si Helpdesk est présent** |
| `ansut_demo` — jeu d'essai | non, jamais automatiquement |
| `ansut_stock` — le module chapeau | — |

`ansut_sav` s'installe **de lui-même** dès que `helpdesk_stock` et
`helpdesk_repair` sont présents. Il exige donc Odoo Enterprise, et reste
volontairement hors des dépendances du chapeau : le socle s'installe aussi sur
une instance communautaire, sans SAV.

## 4. Éprouver la chaîne

`ansut_demo` installe de quoi parcourir tout le circuit sans rien saisir : huit
tablettes sérialisées dont deux hors garantie, cinq bénéficiaires couvrant les
quatre statuts d'éligibilité, deux remises déjà servies et un retrait prêt.

```bash
odoo -d votre_base -i ansut_stock,ansut_demo --stop-after-init
```

Le parcours, dans l'application **ANSUT**, menu *Point de retrait* :

1. le jeton QR se lit sur le retrait `WH/RET/00004`, onglet *Retrait ANSUT* —
   champ réservé aux responsables ;
2. **PIN de démonstration : `123456`** ;
3. saisissez d'abord un mauvais PIN : le compteur descend sans bloquer l'écran ;
4. relevez une pièce d'identité, signez, validez. Le stock sort réellement, et
   le PV de remise s'édite.

> `ansut_demo` pose un PIN connu de tous. **Ne l'installez jamais en
> production**, et désinstallez-le avant toute mise en service.

## Prérequis

- **Odoo 17**, communautaire ou Enterprise.
- **Enterprise avec Helpdesk** pour le SAV (`ansut_sav`) uniquement.
- **wkhtmltopdf** pour les PV de remise. L'image Docker `odoo:17` l'embarque ;
  une installation manuelle peut en manquer. Sans lui, la signature d'un
  transfert échoue, Odoo générant automatiquement le bon de livraison signé.
- Sur une instance Enterprise, **figez communautaire et Enterprise sur la même
  révision** : un décalage entre les deux dépôts empêche certains modules
  standard de s'installer.
