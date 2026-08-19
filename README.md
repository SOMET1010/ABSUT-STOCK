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
| `ansut_theme` | Design System ANSUT (§5–§8, §62) | **Livré** |
| `ansut_dashboard` | Tableaux de bord OWL (§10) | À faire |
| `ansut_beneficiary` | Bénéficiaires (§22) | **Livré** |
| `ansut_distribution` | Distribution, QR et PIN (§19–§29) | **Livré** |
| `ansut_withdrawal` | Point de retrait, remise, PV (§25–§29) | **Livré** |
| `ansut_sav` | SAV, garantie, échange standard (§30–§34) | **Livré** |
| `ansut_api` · `ansut_webhook` | API versionnée et webhooks (§38–§41) | À faire |
| `ansut_audit` · `ansut_reporting` | Journal d'audit et reporting (§45–§48) | À faire |

## Principe : si Odoo l'a, on ne le refait pas

Odoo Stock — et davantage encore en Enterprise — couvre déjà l'essentiel d'une
gestion de parc. Chaque champ de ces modules a donc dû justifier son existence
contre le standard. Ce qui a été **retiré** après vérification dans la source
d'Odoo 17 :

| Ce que j'avais écrit | Ce qu'Odoo faisait déjà |
|---|---|
| Modèle `ansut.distribution` | `stock.picking` : état, destinataire, dates, origine, destination, réservation, mouvements de stock, reliquats, traçabilité |
| Règle « un équipement engagé une seule fois » | La réservation standard (`_action_assign`) |
| `delivery_signature` | `stock.picking.signature` |
| `serial_number` | `stock.lot.name` |
| `current_site_id`, `current_location_id` | `stock.lot.location_id`, `quant_ids` |
| 9 des 13 états du cycle de vie | Position déduite des quants et des transferts |

Le modèle maison ne se contentait pas de redire le standard : **il ne bougeait
jamais le stock**. Un équipement « remis » restait en stock aux yeux d'Odoo,
faussant inventaire, valorisation et traçabilité. Le retrait est désormais un
transfert Odoo à part entière, et sa validation passe par `button_validate()`.

Ce qu'Odoo n'a pas, et que ces modules construisent :

- l'authentification au comptoir d'un bénéficiaire qui **n'est pas un
  utilisateur Odoo**, par QR et PIN indépendants ;
- la qualification, l'éligibilité et le plafond d'équipements d'un
  bénéficiaire ;
- l'identifiant ANSUT, l'IMEI, le marquage physique et la garantie d'un
  équipement, et son état hors circuit logistique (SAV, perdu, hors service) ;
- le PV de remise et ses mentions.

## Ce que couvre `ansut_equipment`

Extension de `stock.lot`, conformément à la matrice §74 qui classe la
sérialisation en standard Odoo avec extension.

- les champs du §12 qu'Odoo n'a pas : identifiant ANSUT, IMEI, référence
  constructeur, numéro d'immobilisation, type de marquage ;
- l'état du §14 **hors circuit logistique** — en service, SAV, en réparation,
  perdu, hors service. La position (en stock, réservé, en transit, livré) est
  celle qu'Odoo calcule : elle n'est pas recopiée dans un champ maison qui
  dériverait au premier mouvement fait hors de nos écrans ;
- la garantie calculée du §33 (`warranty_active`) ;
- le détenteur courant, stocké pour être filtrable — mais **posé par la
  validation du transfert**, jamais saisi à la main ;
- RG-001 (identifiant unique, contrainte SQL) et la cohérence des dates de
  garantie.

## Ce que couvre `ansut_theme`

Jetons du §62 centralisés dans `tokens.scss` : couleurs institutionnelles du
§5, couleurs fonctionnelles du §6 tenues volontairement secondaires, rayons,
ombres, espacements et typographie du §7. Aucun composant ne redéfinit ses
couleurs — c'est la règle posée par le §62.

Les variables primaires surchargent Bootstrap avant son chargement, ce qui
reteinte l'ossature du Web Client : barre supérieure, surfaces, boutons,
badges d'état, onglets, et un focus visible conforme au §63.

Les valeurs sont dérivées des maquettes de référence validées.

## Ce que couvre `ansut_beneficiary`

Le bénéficiaire reste un `res.partner` étendu, pour garder les adresses, les
contacts et les communications standard d'Odoo.

- qualification explicite (`is_ansut_beneficiary`), identifiant unique attribué
  à la qualification et non à la création du contact ;
- catégories porteuses d'un **plafond d'équipements**, alimentées par cinq
  entrées de départ ajustables par le métier ;
- statut d'éligibilité à quatre états — à vérifier, vérifié, suspendu, sorti
  du dispositif — la vérification exigeant une pièce d'identité ;
- deux règles opposables au retrait : **RG-009** (seul un bénéficiaire vérifié
  reçoit un équipement) et **RG-010** (plafond de la catégorie), le décompte
  ignorant les équipements perdus ou hors service ;
- un motif de non-éligibilité lisible, affiché en bandeau sur la fiche contact
  comme sur le transfert.

## Ce que couvre `ansut_withdrawal`

L'écran agent du point de retrait, en quatre temps sans raccourci possible :
scanner le QR, saisir le PIN, contrôler l'identité, remettre l'équipement.

- l'assistant est transitoire : ni le PIN ni le jeton lu n'y survivent — le
  jeton est effacé dès qu'il est résolu, le PIN dès qu'il est vérifié ;
- la résolution du QR ne distingue jamais « jeton inconnu » de « retrait déjà
  clôturé », pour ne pas faire du point de retrait un oracle à jetons ; elle
  refuse aussi les retraits expirés ;
- les preuves vont sur le transfert, qui est l'enregistrement d'audit, et la
  validation passe par `button_validate()` : le stock sort réellement ;
- le **PV de remise** du §29 : référence, bénéficiaire, pièce présentée,
  équipements avec IMEI et garantie, photo, signatures. Il ne s'édite qu'après
  la remise effective.

## Ce que couvre `ansut_sav`

Le module le plus mince du lot, et c'est voulu : Odoo Enterprise fait presque
tout. `helpdesk_stock` donne déjà au ticket le numéro de série, les produits
réellement livrés au demandeur et les bons de retour ; `helpdesk_repair` le
lien vers les ordres de réparation ; `repair` (communautaire) les ordres
eux-mêmes, pièces et mouvements de stock compris. Rien de cela n'est réécrit.

Ce que le standard ne sait pas, et qui est ajouté :

- **la garantie au moment du ticket** — `repair.order` a bien un indicateur
  `under_warranty`, mais il faut le cocher à la main. Il est désormais déduit
  de la garantie de l'équipement, tout en restant modifiable : un geste
  commercial hors garantie doit rester possible ;
- **la cohérence demandeur / détenteur** : un ticket ouvert par quelqu'un
  d'autre que le détenteur enregistré est signalé avant toute prise en charge ;
- **la répercussion sur l'état de l'équipement** : ouvrir un ticket le place en
  SAV, démarrer une réparation le passe en réparation, la terminer le remet en
  service — sans jamais écraser un état plus grave, un équipement déclaré perdu
  ne redevenant pas « en SAV » ;
- **l'échange standard du §34** : le bénéficiaire repart avec un équipement de
  remplacement pendant que le sien part en SAV. Le remplacement n'est pas une
  livraison ordinaire — il suit la même procédure sécurisée que la remise
  initiale, QR et PIN compris, parce que c'est le même geste au même comptoir.
  RG-009 s'y applique : un bénéficiaire suspendu ne repart pas avec du
  matériel.

## Démarrer une instance locale

```bash
docker compose up -d
docker compose run --rm odoo odoo -d ansut \
  -i ansut_theme,ansut_equipment,ansut_beneficiary,ansut_distribution,ansut_withdrawal \
  --stop-after-init

# Les tests des modules, sur la même instance
docker compose run --rm odoo odoo -d ansut \
  -u ansut_beneficiary,ansut_withdrawal --test-enable \
  --test-tags /ansut_beneficiary,/ansut_withdrawal --stop-after-init
```

Puis <http://localhost:8069>, avec `admin` / `admin`.

## Tester en dix minutes

Le module `ansut_demo` installe de quoi parcourir la chaîne sans rien saisir :
huit tablettes sérialisées (dont deux hors garantie), cinq bénéficiaires
couvrant les quatre statuts d'éligibilité, deux remises déjà servies et **un
retrait prêt à être servi**.

```bash
docker compose up -d
docker compose run --rm odoo odoo -d ansut \
  -i ansut_theme,ansut_equipment,ansut_beneficiary,ansut_distribution,\
ansut_withdrawal,ansut_demo --stop-after-init
```

Puis <http://localhost:8069>, `admin` / `admin`, application **ANSUT**.

Le parcours à suivre, menu *Point de retrait* :

1. le jeton QR du retrait prêt se lit dans le formulaire du retrait
   `WH/RET/00004`, onglet *Retrait ANSUT* (champ réservé aux responsables) ;
2. **PIN de démonstration : `123456`** ;
3. saisissez un mauvais PIN d'abord — le compteur descend sans bloquer l'écran ;
4. relevez une pièce d'identité, signez, validez : le stock sort réellement, et
   le PV de remise s'édite.

> `ansut_demo` pose un PIN connu. **Ne l'installez jamais en production.**

## Validé sur une instance réelle

Les modules ne sont pas seulement analysés : ils sont installés et testés sur
une instance Odoo 17 montée pour l'occasion (PostgreSQL local + source Odoo,
Docker étant hors d'atteinte derrière la politique réseau).

| | Communautaire | Communautaire + Enterprise |
|---|---|---|
| Installation | 4 modules ✅ | 5 modules ✅ |
| Tests `ansut_beneficiary` | 11 ✅ | 11 ✅ |
| Tests `ansut_withdrawal` | 19 ✅ | 19 ✅ |
| Tests `ansut_sav` | — (exige Helpdesk) | 15 ✅ |

La pile Enterprise testée comprend `helpdesk`, `helpdesk_stock`,
`helpdesk_repair`, `stock_barcode` et `web_enterprise` installés aux côtés des
modules ANSUT : aucun conflit, aucune erreur. `ansut_sav` est le seul module du
lot qui exige Enterprise — les quatre autres tournent en communautaire.

## Une contrainte à connaître

**Alignez les révisions.** Le lot Enterprise disponible date de novembre 2025,
la branche communautaire 17.0 vit toujours. Le module `sign` de ce lot appelle
`PdfFileReader(..., overwriteWarnings=...)`, argument que la version de PyPDF2
épinglée par Odoo 17 a supprimé : `sign` ne s'installe pas contre un
communautaire plus récent. Une instance de production doit figer communautaire
et Enterprise sur la **même** révision. Rien de tout cela ne touche aux modules
ANSUT, qui n'en dépendent pas.

**OWL, pas React.** Le §79 écarte explicitement un frontend React indépendant.
Les interfaces métier sont à développer en OWL, intégré au Web Client Odoo.
L'atelier `odoo-react-alchemy` sert à maquetter les 21 écrans du §77 pour
validation avant développement, pas à produire le code livré.
