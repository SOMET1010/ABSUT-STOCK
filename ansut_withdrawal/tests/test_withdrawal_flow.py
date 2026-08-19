# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged

#: Image PNG 1×1 valide, encodée en base64 : sert de photo et de signature.
PIXEL = (b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
         b"IQAAAABJRU5ErkJggg==")


@tagged('post_install', '-at_install')
class TestWithdrawalFlow(TransactionCase):
    """Parcours agent du point de retrait (§25 à §29).

    Le retrait est un transfert Odoo : chaque test part d'un vrai
    `stock.picking` réservé, et la remise doit sortir l'équipement du stock.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        categorie = cls.env['ansut.beneficiary.category'].create({
            'name': "Test retrait", 'code': 'TEST_RETRAIT', 'equipment_limit': 0,
        })
        cls.beneficiaire = cls.env['res.partner'].create({
            'name': "Bénéficiaire du retrait",
            'is_ansut_beneficiary': True,
            'beneficiary_category_id': categorie.id,
            'identity_document_type': 'cni',
            'identity_document_number': 'CI-9999',
        })
        cls.beneficiaire.action_verify_beneficiary()

        cls.produit = cls.env['product.product'].create({
            'name': "Tablette de retrait", 'type': 'product', 'tracking': 'serial',
        })
        cls.type_retrait = cls.env.ref('ansut_distribution.picking_type_ansut_withdrawal')
        # Sans mise en page choisie, Odoo détourne toute impression vers son
        # assistant de configuration : on la fixe pour éprouver le vrai PV.
        cls.env.company.external_report_layout_id = cls.env.ref('web.external_layout_standard')
        cls.emplacement_stock = cls.type_retrait.default_location_src_id
        cls.compteur = 0

    def _equipement_en_stock(self):
        """Crée un numéro de série et le met physiquement en stock."""
        type(self).compteur += 1
        lot = self.env['stock.lot'].create({
            'name': f"SN-RETRAIT-{self.compteur:03d}",
            'product_id': self.produit.id,
        })
        self.env['stock.quant']._update_available_quantity(
            self.produit, self.emplacement_stock, 1, lot_id=lot)
        return lot

    def _retrait(self):
        """Transfert de retrait confirmé et réservé, QR et PIN générés."""
        lot = self._equipement_en_stock()
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.type_retrait.id,
            'partner_id': self.beneficiaire.id,
            'location_id': self.type_retrait.default_location_src_id.id,
            'location_dest_id': self.type_retrait.default_location_dest_id.id,
            'move_ids': [(0, 0, {
                'name': self.produit.name,
                'product_id': self.produit.id,
                'product_uom_qty': 1,
                'product_uom': self.produit.uom_id.id,
                'location_id': self.type_retrait.default_location_src_id.id,
                'location_dest_id': self.type_retrait.default_location_dest_id.id,
            })],
        })
        picking.action_confirm()
        picking.action_assign()
        picking.move_ids.move_line_ids.write({'lot_id': lot.id, 'quantity': 1})
        picking.action_issue_secrets()
        return picking, lot

    def _jeton(self, picking):
        # Le jeton est réservé aux responsables : les tests le lisent en sudo.
        return picking.sudo().qr_token

    def _assistant(self):
        return self.env['ansut.withdrawal.wizard'].create({})

    # --- Le retrait s'appuie bien sur le standard -----------------------------
    def test_le_retrait_est_un_transfert(self):
        picking, lot = self._retrait()
        self.assertTrue(picking.is_ansut_withdrawal)
        self.assertEqual(picking.state, 'assigned', "la réservation standard doit s'appliquer")
        self.assertIn(lot, picking.ansut_equipment_ids)

    def test_reservation_standard_empeche_le_double_engagement(self):
        """Odoo réserve la quantité : le même numéro de série ne peut pas être
        promis deux fois. Aucune règle maison ne réécrit ce contrôle."""
        picking, lot = self._retrait()
        second = self.env['stock.picking'].create({
            'picking_type_id': self.type_retrait.id,
            'partner_id': self.beneficiaire.id,
            'location_id': self.type_retrait.default_location_src_id.id,
            'location_dest_id': self.type_retrait.default_location_dest_id.id,
            'move_ids': [(0, 0, {
                'name': self.produit.name,
                'product_id': self.produit.id,
                'product_uom_qty': 1,
                'product_uom': self.produit.uom_id.id,
                'location_id': self.type_retrait.default_location_src_id.id,
                'location_dest_id': self.type_retrait.default_location_dest_id.id,
            })],
        })
        second.action_confirm()
        second.action_assign()
        self.assertNotIn(lot, second.move_ids.move_line_ids.lot_id)

    # --- Étape 1 : le QR ------------------------------------------------------
    def test_qr_inconnu_refuse(self):
        assistant = self._assistant()
        assistant.qr_token = 'jeton-inexistant'
        with self.assertRaises(UserError):
            assistant.action_scan()

    def test_qr_vide_refuse(self):
        with self.assertRaises(UserError):
            self._assistant().action_scan()

    def test_qr_expire_refuse(self):
        picking, _lot = self._retrait()
        picking.withdrawal_expiration = fields.Datetime.now() - timedelta(days=1)
        assistant = self._assistant()
        assistant.qr_token = self._jeton(picking)
        with self.assertRaises(UserError):
            assistant.action_scan()

    def test_scan_resout_le_retrait_et_efface_le_jeton(self):
        picking, _lot = self._retrait()
        assistant = self._assistant()
        assistant.qr_token = self._jeton(picking)
        assistant.action_scan()

        self.assertEqual(assistant.picking_id, picking)
        self.assertEqual(assistant.step, 'pin')
        self.assertFalse(assistant.qr_token, "le jeton lu ne survit pas à sa résolution")

    # --- Étape 2 : le PIN -----------------------------------------------------
    def test_pin_faux_decompte_les_tentatives(self):
        """Le compteur doit survivre à l'échec.

        Un PIN faux qui lèverait une erreur annulerait la transaction — et le
        compteur avec elle : le verrou après trois essais ne verrouillerait
        jamais rien. L'échec est donc signalé sans lever.
        """
        picking, _lot = self._retrait()
        assistant = self._assistant()
        assistant.qr_token = self._jeton(picking)
        assistant.action_scan()

        for attendu in (2, 1, 0):
            assistant.pin = '000000'
            assistant.action_verify_pin()
            self.assertEqual(assistant.step, 'pin', "un PIN faux ne fait pas avancer")
            self.assertIn(str(attendu), assistant.pin_error)

        self.assertEqual(picking.pin_attempts, 3)
        self.assertTrue(picking.pin_blocked)

        # Une fois bloqué, même le bon PIN ne passe plus.
        with self.assertRaises(UserError):
            picking.verify_pin('000000')

    def _jusqu_au_controle(self):
        """Amène un retrait jusqu'au contrôle d'identité, PIN vérifié."""
        picking, lot = self._retrait()
        pin = '123456'
        # Le PIN en clair n'est pas conservé : on repose l'empreinte attendue.
        picking.sudo().pin_hash = picking._hash_pin(pin)

        assistant = self._assistant()
        assistant.qr_token = self._jeton(picking)
        assistant.action_scan()
        assistant.pin = pin
        assistant.action_verify_pin()
        return picking, lot, assistant

    def test_pin_juste_ouvre_le_controle(self):
        picking, _lot, assistant = self._jusqu_au_controle()
        self.assertEqual(assistant.step, 'check')
        self.assertEqual(picking.withdrawal_state, 'checking')
        self.assertFalse(assistant.pin, "le PIN saisi ne reste pas dans l'assistant")

    # --- Étape 3 : la remise --------------------------------------------------
    def test_remise_exige_la_signature(self):
        _picking, _lot, assistant = self._jusqu_au_controle()
        assistant.identity_document_number = 'CI-9999'
        with self.assertRaises(UserError):
            assistant.action_deliver()

    def test_remise_exige_la_piece(self):
        _picking, _lot, assistant = self._jusqu_au_controle()
        assistant.delivery_signature = PIXEL
        with self.assertRaises(UserError):
            assistant.action_deliver()

    def _remettre(self, assistant):
        assistant.write({
            'identity_document_number': 'CI-9999',
            'delivery_signature': PIXEL,
            'delivery_photo': PIXEL,
        })
        return assistant.action_deliver()

    def test_remise_sort_reellement_l_equipement_du_stock(self):
        """Le point qu'un modèle maison manquait : le stock bouge."""
        picking, lot, assistant = self._jusqu_au_controle()
        # `product_qty` est la quantité détenue : la quantité *disponible*, elle,
        # est déjà nulle puisque la réservation standard a retenu le numéro.
        self.assertEqual(lot.product_qty, 1)

        self._remettre(assistant)

        self.assertEqual(picking.state, 'done')
        self.assertEqual(picking.withdrawal_state, 'delivered')
        lot.invalidate_recordset()
        self.assertEqual(lot.product_qty, 0, "l'équipement doit avoir quitté le stock")
        # Le détenteur est dérivé du transfert validé, pas saisi à la main.
        lot.invalidate_recordset()
        self.assertEqual(lot.beneficiary_id, self.beneficiaire)

    def test_remise_ecrit_les_preuves_sur_le_transfert(self):
        picking, _lot, assistant = self._jusqu_au_controle()
        self._remettre(assistant)

        self.assertTrue(picking.signature, "la signature standard du transfert est utilisée")
        self.assertTrue(picking.delivery_photo)
        self.assertEqual(picking.identity_document_number, 'CI-9999')
        # QR et PIN sont invalidés par la remise (§24).
        self.assertFalse(picking.sudo().qr_token)
        self.assertFalse(picking.sudo().pin_hash)

    def test_retrait_cloture_nest_plus_scannable(self):
        picking, _lot, assistant = self._jusqu_au_controle()
        jeton = self._jeton(picking)
        self._remettre(assistant)

        suivant = self._assistant()
        suivant.qr_token = jeton
        with self.assertRaises(UserError):
            suivant.action_scan()

    def test_remise_non_rejouable(self):
        """RG-005 : une remise clôturée ne se rejoue pas."""
        picking, _lot, assistant = self._jusqu_au_controle()
        self._remettre(assistant)
        with self.assertRaises(UserError):
            picking.button_validate()

    # --- Étape 4 : le PV ------------------------------------------------------
    def test_pv_refuse_avant_la_remise(self):
        picking, _lot = self._retrait()
        with self.assertRaises(UserError):
            picking.action_print_withdrawal_report()

    def test_pv_edite_apres_la_remise(self):
        picking, lot, assistant = self._jusqu_au_controle()
        self._remettre(assistant)

        action = picking.action_print_withdrawal_report()
        self.assertEqual(action['type'], 'ir.actions.report')

        rendu = self.env['ir.actions.report']._render_qweb_html(
            'ansut_withdrawal.report_withdrawal', picking.ids)[0]
        self.assertIn(picking.name.encode(), rendu)
        self.assertIn(lot.name.encode(), rendu)
