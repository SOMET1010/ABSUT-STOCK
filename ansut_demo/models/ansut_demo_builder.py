# -*- coding: utf-8 -*-
"""Construction du jeu d'essai ANSUT.

Le parcours de retrait ne se laisse pas décrire en XML : il faut mettre des
numéros de série en stock, confirmer et réserver des transferts, puis poser
un PIN dont on connaît la valeur. C'est fait ici, en Python, à l'installation.

Le PIN de démonstration est volontairement connu — c'est tout l'objet du
module : permettre à un testeur d'aller au bout du parcours agent. Aucun
module de production ne doit en dépendre.
"""
import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

#: PIN posé sur les retraits de démonstration.
DEMO_PIN = '123456'

#: Bénéficiaires du jeu d'essai : nom, catégorie, statut, pièce.
BENEFICIAIRES = [
    ("École primaire de Yopougon", 'category_school', 'verified', 'attestation', 'ATT-2026-0011'),
    ("Centre de santé d'Abobo", 'category_health', 'verified', 'attestation', 'ATT-2026-0042'),
    ("Konan Aya", 'category_individual', 'verified', 'cni', 'CI-0293847'),
    ("Traoré Ibrahim", 'category_individual', 'draft', 'cni', 'CI-0384756'),
    ("Diabaté Fatou", 'category_agent', 'suspended', 'cni', 'CI-0475869'),
]


class AnsutDemoBuilder(models.AbstractModel):
    """Point d'entrée appelé par les données du module."""

    _name = 'ansut.demo.builder'
    _description = "Générateur du jeu d'essai ANSUT"

    # --- Point d'entrée -------------------------------------------------------
    @api.model
    def build(self):
        produit = self._produit()
        beneficiaires = self._beneficiaires()
        equipements = self._equipements(produit, nombre=8)

        # Deux équipements déjà remis, pour que le parc ne soit pas vierge.
        self._remise_passee(produit, equipements[0], beneficiaires[0])
        self._remise_passee(produit, equipements[1], beneficiaires[2])

        # Un retrait prêt à servir : QR et PIN générés, PIN connu du testeur.
        pret = self._retrait_pret(produit, equipements[2], beneficiaires[0])

        _logger.info(
            "Jeu d'essai ANSUT installé — retrait %s prêt, PIN de démonstration %s",
            pret.name, DEMO_PIN)
        return True

    # --- Briques --------------------------------------------------------------
    def _produit(self):
        produit = self.env['product.product'].search(
            [('default_code', '=', 'ANSUT-TAB10')], limit=1)
        if produit:
            return produit
        return self.env['product.product'].create({
            'name': "Tablette ANSUT 10 pouces",
            'default_code': 'ANSUT-TAB10',
            'type': 'product',
            'tracking': 'serial',
            'list_price': 85000.0,
        })

    def _beneficiaires(self):
        crees = self.env['res.partner']
        for nom, categorie, statut, type_piece, numero in BENEFICIAIRES:
            existant = self.env['res.partner'].search([('name', '=', nom)], limit=1)
            if existant:
                crees |= existant
                continue
            partenaire = self.env['res.partner'].create({
                'name': nom,
                'is_ansut_beneficiary': True,
                'beneficiary_category_id': self.env.ref(
                    f'ansut_beneficiary.{categorie}').id,
                'identity_document_type': type_piece,
                'identity_document_number': numero,
                'country_id': self.env.ref('base.ci', raise_if_not_found=False).id or False,
            })
            # Le statut passe par les transitions, pas par une écriture directe :
            # le jeu d'essai emprunte les mêmes chemins que l'exploitation.
            if statut == 'verified':
                partenaire.action_verify_beneficiary()
            elif statut == 'suspended':
                partenaire.action_verify_beneficiary()
                partenaire.action_suspend_beneficiary()
            crees |= partenaire
        return crees

    def _equipements(self, produit, nombre):
        type_retrait = self._type_retrait()
        equipements = self.env['stock.lot']
        for indice in range(nombre):
            serie = f"ANSUT-TAB-{indice + 1:04d}"
            lot = self.env['stock.lot'].search(
                [('name', '=', serie), ('product_id', '=', produit.id)], limit=1)
            if not lot:
                lot = self.env['stock.lot'].create({
                    'name': serie,
                    'product_id': produit.id,
                    'imei': f"3566{indice + 1:011d}",
                    'manufacturer_reference': f"TAB10-{indice + 1:04d}",
                    'asset_number': f"IMMO-{indice + 1:05d}",
                    # Un équipement sur quatre est plus ancien et sa garantie
                    # est échue, pour éprouver l'alerte du SAV.
                    **(
                        {'acquisition_date': '2022-11-10',
                         'commissioning_date': '2022-12-01',
                         'warranty_start': '2022-12-01',
                         'warranty_end': '2024-12-01'}
                        if indice % 4 == 3 else
                        {'acquisition_date': '2026-01-15',
                         'commissioning_date': '2026-02-01',
                         'warranty_start': '2026-02-01',
                         'warranty_end': '2028-02-01'}
                    ),
                })
                self.env['stock.quant']._update_available_quantity(
                    produit, type_retrait.default_location_src_id, 1, lot_id=lot)
            equipements |= lot
        return equipements

    def _type_retrait(self):
        return self.env.ref('ansut_distribution.picking_type_ansut_withdrawal')

    def _retrait(self, produit, equipement, beneficiaire):
        """Transfert de retrait confirmé, réservé sur le numéro de série voulu."""
        type_retrait = self._type_retrait()
        source = type_retrait.default_location_src_id
        destination = type_retrait.default_location_dest_id

        retrait = self.env['stock.picking'].create({
            'picking_type_id': type_retrait.id,
            'partner_id': beneficiaire.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': "Jeu d'essai ANSUT",
            'move_ids': [fields.Command.create({
                'name': produit.display_name,
                'product_id': produit.id,
                'product_uom_qty': 1,
                'product_uom': produit.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })],
        })
        retrait.action_confirm()
        retrait.action_assign()

        lignes = retrait.move_ids.move_line_ids
        if not lignes:
            _logger.warning("Aucune ligne réservée pour %s", equipement.display_name)
            return retrait
        lignes[1:].unlink()
        lignes[0].write({'lot_id': equipement.id, 'quantity': 1})
        return retrait

    def _poser_pin_connu(self, retrait):
        """Remplace le PIN aléatoire par celui que le testeur connaît."""
        retrait.action_issue_secrets()
        retrait.sudo().pin_hash = retrait._hash_pin(DEMO_PIN)
        return retrait

    def _retrait_pret(self, produit, equipement, beneficiaire):
        retrait = self._retrait(produit, equipement, beneficiaire)
        return self._poser_pin_connu(retrait)

    def _remise_passee(self, produit, equipement, beneficiaire):
        """Retrait déjà servi : le parc démarre avec un historique."""
        retrait = self._retrait(produit, equipement, beneficiaire)
        self._poser_pin_connu(retrait)
        retrait.verify_pin(DEMO_PIN)
        retrait.write({
            'identity_document_type': beneficiaire.identity_document_type,
            'identity_document_number': beneficiaire.identity_document_number,
            'signature': SIGNATURE_DEMO,
        })
        retrait.button_validate()
        return retrait


#: Signature de démonstration : une image PNG 1×1 valide.
SIGNATURE_DEMO = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    b"IQAAAABJRU5ErkJggg==")
