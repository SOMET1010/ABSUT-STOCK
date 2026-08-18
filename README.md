# ANSUT Stock

Plateforme de gestion des stocks d'équipements de l'ANSUT, sur Odoo 17.

Mise en œuvre du *Dossier de Spécifications Détaillées* v1.0 : cycle de vie
complet d'un équipement de la réception à la sortie définitive, traçabilité
unitaire, multi-sites, distribution contrôlée aux bénéficiaires, SAV, API.

## État d'avancement

| Module | Objet | État |
| --- | --- | --- |
| `ansut_equipment` | Référentiel équipement unitaire (DSD §11–§14, §23, §33) | **Livré** |
| `ansut_core` | Socle commun, séquences, constantes | À faire |
| `ansut_theme` | Design System ANSUT (§5–§8, §62) | À faire |
| `ansut_dashboard` | Tableaux de bord OWL (§10) | À faire |
| `ansut_beneficiary` | Bénéficiaires (§22) | À faire |
| `ansut_distribution` | Distribution, QR et PIN (§19–§24) | À faire |
| `ansut_withdrawal` | Point de retrait, remise, PV (§25–§29) | À faire |
| `ansut_sav` | SAV, garantie, échange standard (§30–§34) | À faire |
| `ansut_api` · `ansut_webhook` | API versionnée et webhooks (§38–§41) | À faire |
| `ansut_audit` · `ansut_reporting` | Journal d'audit et reporting (§45–§48) | À faire |

## Ce que couvre `ansut_equipment`

Extension de `stock.lot`, conformément à la matrice §74 qui classe la
sérialisation en standard Odoo avec extension.

- les 15 champs du §12 : identifiant ANSUT, IMEI, référence constructeur,
  numéro d'immobilisation, jeton QR, dates, garantie, bénéficiaire, site ;
- le cycle de vie à 13 états du §14, branches SAV et rebut comprises ;
- la garantie calculée du §33 (`warranty_active`) ;
- le jeton QR du §23 : opaque, non prédictible, révocable, sans donnée
  personnelle ;
- trois règles critiques du §71 — RG-001 (identifiant unique, contrainte SQL),
  RG-003 (pas d'attribution sans bénéficiaire), cohérence des dates de
  garantie.

## Démarrer une instance locale

```bash
docker compose up -d
docker compose run --rm odoo odoo -d ansut -i ansut_equipment --stop-after-init
```

Puis <http://localhost:8069>, avec `admin` / `admin`.

## Deux contraintes à connaître

**Odoo Enterprise.** Le §30 fonde le SAV sur Helpdesk et le §26 évoque Odoo
Sign : ce sont des modules Enterprise. La pile Docker de ce dépôt utilise
l'image communautaire `odoo:17` et ne pourra pas les installer. Une image
Enterprise sous licence sera nécessaire pour les lots SAV et signature.

**OWL, pas React.** Le §79 écarte explicitement un frontend React indépendant.
Les interfaces métier sont à développer en OWL, intégré au Web Client Odoo.
L'atelier `odoo-react-alchemy` sert à maquetter les 21 écrans du §77 pour
validation avant développement, pas à produire le code livré.
