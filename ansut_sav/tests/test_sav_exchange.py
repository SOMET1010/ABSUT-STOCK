# -*- coding: utf-8 -*-
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSavExchange(TransactionCase):
    """SAV, garantie et échange standard (§30 à §34)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        categorie = cls.env['ansut.beneficiary.category'].create({
            'name': "Test SAV", 'code': 'TEST_SAV', 'equipment_limit': 0,
        })
        cls.beneficiaire = cls.env['res.partner'].create({
            'name': "Bénéficiaire SAV",
            'is_ansut_beneficiary': True,
            'beneficiary_category_id': categorie.id,
            'identity_document_type': 'cni',
            'identity_document_number': 'CI-SAV',
        })
        cls.beneficiaire.action_verify_beneficiary()

        cls.produit = cls.env['product.product'].create({
            'name': "Tablette SAV", 'type': 'product', 'tracking': 'serial',
        })
        cls.type_retrait = cls.env.ref('ansut_distribution.picking_type_ansut_withdrawal')
        cls.equipe = cls.env['helpdesk.team'].create({'name': "SAV ANSUT"})
        cls.compteur = 0

    def _equipement(self, en_stock=True, garantie=True, detenteur=None):
        type(self).compteur += 1
        lot = self.env['stock.lot'].create({
            'name': f"SN-SAV-{self.compteur:03d}",
            'product_id': self.produit.id,
            'warranty_start': '2020-01-01',
            'warranty_end': '2999-12-31' if garantie else '2021-01-01',
        })
        if en_stock:
            self.env['stock.quant']._update_available_quantity(
                self.produit, self.type_retrait.default_location_src_id, 1, lot_id=lot)
        if detenteur:
            self.env.cr.execute(
                "UPDATE stock_lot SET beneficiary_id = %s WHERE id = %s", (detenteur.id, lot.id))
            lot.invalidate_recordset(['beneficiary_id'])
        return lot

    def _ticket(self, lot, demandeur=None):
        return self.env['helpdesk.ticket'].create({
            'name': f"Panne {lot.name}",
            'team_id': self.equipe.id,
            'partner_id': (demandeur or self.beneficiaire).id,
            'product_id': self.produit.id,
            'lot_id': lot.id,
        })

    # --- Rattachement au parc -------------------------------------------------
    def test_ticket_reprend_les_donnees_du_parc(self):
        """Le ticket lit le parc : rien n'est ressaisi."""
        lot = self._equipement(detenteur=self.beneficiaire)
        ticket = self._ticket(lot)

        self.assertTrue(ticket.is_ansut_equipment)
        self.assertEqual(ticket.equipment_uid, lot.equipment_uid)
        self.assertTrue(ticket.equipment_warranty_active)
        self.assertEqual(ticket.equipment_beneficiary_id, self.beneficiaire)

    def test_ouverture_du_ticket_place_l_equipement_en_sav(self):
        lot = self._equipement(detenteur=self.beneficiaire)
        self.assertEqual(lot.ansut_condition, 'operational')

        self._ticket(lot)
        lot.invalidate_recordset()
        self.assertEqual(lot.ansut_condition, 'after_sales')

    def test_ticket_n_ecrase_pas_un_etat_plus_grave(self):
        """Un équipement déjà déclaré perdu ne redevient pas « en SAV »."""
        lot = self._equipement(detenteur=self.beneficiaire)
        lot.ansut_condition = 'lost'

        self._ticket(lot)
        lot.invalidate_recordset()
        self.assertEqual(lot.ansut_condition, 'lost')

    def test_hors_garantie_signale(self):
        lot = self._equipement(garantie=False, detenteur=self.beneficiaire)
        ticket = self._ticket(lot)
        self.assertFalse(ticket.equipment_warranty_active)

    def test_demandeur_different_du_detenteur(self):
        autre = self.env['res.partner'].create({'name': "Quelqu'un d'autre"})
        lot = self._equipement(detenteur=self.beneficiaire)
        ticket = self._ticket(lot, demandeur=autre)
        self.assertTrue(ticket.beneficiary_mismatch)

    def test_pas_d_action_sav_hors_parc(self):
        hors_parc = self.env['stock.lot'].create({
            'name': "SN-HORS-PARC", 'product_id': self.produit.id,
        })
        # Les équipements hors parc n'ont pas d'identifiant ANSUT.
        hors_parc.equipment_uid = False
        ticket = self._ticket(hors_parc)
        self.assertFalse(ticket.is_ansut_equipment)
        with self.assertRaises(UserError):
            ticket.action_ansut_declare_out_of_order()

    # --- Réparation -----------------------------------------------------------
    def test_garantie_deduite_sur_l_ordre_de_reparation(self):
        """`under_warranty` ne se coche plus à la main."""
        sous_garantie = self._equipement(detenteur=self.beneficiaire)
        echue = self._equipement(garantie=False, detenteur=self.beneficiaire)

        for lot, attendu in ((sous_garantie, True), (echue, False)):
            reparation = self.env['repair.order'].create({
                'product_id': self.produit.id,
                'lot_id': lot.id,
                'partner_id': self.beneficiaire.id,
            })
            self.assertEqual(reparation.under_warranty, attendu, lot.name)

    def test_geste_commercial_reste_possible(self):
        echue = self._equipement(garantie=False, detenteur=self.beneficiaire)
        reparation = self.env['repair.order'].create({
            'product_id': self.produit.id, 'lot_id': echue.id,
            'partner_id': self.beneficiaire.id,
        })
        reparation.under_warranty = True
        self.assertTrue(reparation.under_warranty)

    # --- Échange standard -----------------------------------------------------
    def _echange(self, **valeurs):
        defaillant = valeurs.pop('defaillant', None) or self._equipement(
            en_stock=False, detenteur=self.beneficiaire)
        remplacement = valeurs.pop('remplacement', None) or self._equipement()
        ticket = self._ticket(defaillant)
        assistant = self.env['ansut.exchange.wizard'].create({
            'ticket_id': ticket.id,
            'replacement_lot_id': remplacement.id,
            **valeurs,
        })
        return defaillant, remplacement, ticket, assistant

    def test_echange_cree_un_retrait_securise(self):
        defaillant, remplacement, ticket, assistant = self._echange()
        action = assistant.action_exchange()

        retrait = self.env['stock.picking'].browse(action['res_id'])
        self.assertTrue(retrait.is_ansut_withdrawal)
        self.assertEqual(retrait.partner_id, self.beneficiaire)
        self.assertIn(remplacement, retrait.ansut_equipment_ids)
        # Le remplacement passe par la même procédure que la remise initiale.
        self.assertEqual(retrait.withdrawal_state, 'secrets_issued')
        self.assertTrue(retrait.sudo().qr_token)
        self.assertTrue(retrait.sudo().pin_hash)
        # Le retrait est rattaché au ticket, via le champ standard de helpdesk.
        self.assertIn(retrait, ticket.picking_ids)

    def test_echange_bascule_l_equipement_defaillant(self):
        defaillant, _remplacement, _ticket, assistant = self._echange(
            faulty_condition='out_of_order')
        assistant.action_exchange()

        defaillant.invalidate_recordset()
        self.assertEqual(defaillant.ansut_condition, 'out_of_order')
        self.assertFalse(defaillant.in_circulation)

    def test_echange_refuse_un_beneficiaire_suspendu(self):
        """RG-009 vaut aussi pour un échange."""
        _defaillant, _remplacement, _ticket, assistant = self._echange()
        self.beneficiaire.action_suspend_beneficiary()
        with self.assertRaises(ValidationError):
            assistant.action_exchange()

    def test_echange_refuse_le_meme_equipement(self):
        defaillant = self._equipement(detenteur=self.beneficiaire)
        with self.assertRaises(UserError):
            self._echange(defaillant=defaillant, remplacement=defaillant)

    def test_echange_refuse_sans_detenteur(self):
        orphelin = self._equipement(en_stock=False)
        _d, _r, _t, assistant = self._echange(defaillant=orphelin)
        with self.assertRaises(UserError):
            assistant.action_exchange()
