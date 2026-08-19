# -*- coding: utf-8 -*-
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestBeneficiaryEligibility(TransactionCase):
    """Éligibilité d'un bénéficiaire : RG-009 et RG-010 (§22)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.categorie_plafonnee = cls.env['ansut.beneficiary.category'].create({
            'name': "Particulier (test)", 'code': 'TEST_PART', 'equipment_limit': 1,
        })
        cls.categorie_libre = cls.env['ansut.beneficiary.category'].create({
            'name': "Structure (test)", 'code': 'TEST_STRUCT', 'equipment_limit': 0,
        })
        cls.produit = cls.env['product.product'].create({
            'name': "Tablette de test", 'type': 'product', 'tracking': 'serial',
        })

    def _beneficiaire(self, categorie=None, **valeurs):
        defauts = {
            'name': "Bénéficiaire de test",
            'is_ansut_beneficiary': True,
            'beneficiary_category_id': (categorie or self.categorie_plafonnee).id,
            'identity_document_type': 'cni',
            'identity_document_number': 'CI-0001',
        }
        defauts.update(valeurs)
        return self.env['res.partner'].create(defauts)

    def _equipement(self, beneficiaire, condition='operational', suffixe=''):
        """Crée un équipement déjà détenu par le bénéficiaire.

        `beneficiary_id` est calculé depuis les livraisons validées : le test
        pose donc le champ en écriture directe sur le champ calculé stocké,
        ce qu'Odoo autorise pour un calcul sans inverse tant que la dépendance
        n'est pas recalculée. Le parcours complet (transfert réel) est couvert
        par les tests de `ansut_withdrawal`.
        """
        lot = self.env['stock.lot'].create({
            'name': f"SN-{beneficiaire.id}-{condition}-{suffixe or self.env['stock.lot'].search_count([])}",
            'product_id': self.produit.id,
            'ansut_condition': condition,
        })
        self.env.cr.execute(
            "UPDATE stock_lot SET beneficiary_id = %s WHERE id = %s",
            (beneficiaire.id, lot.id))
        lot.invalidate_recordset(['beneficiary_id'])
        return lot

    def test_identifiant_attribue_a_la_qualification(self):
        """L'identifiant vient avec la qualification, pas avec le contact."""
        simple = self.env['res.partner'].create({'name': "Contact ordinaire"})
        self.assertFalse(simple.beneficiary_uid)

        simple.write({
            'is_ansut_beneficiary': True,
            'beneficiary_category_id': self.categorie_libre.id,
        })
        self.assertTrue(simple.beneficiary_uid)

    def test_categorie_obligatoire(self):
        with self.assertRaises(ValidationError):
            self.env['res.partner'].create({
                'name': "Sans catégorie", 'is_ansut_beneficiary': True,
            })

    def test_non_verifie_non_eligible(self):
        """RG-009 : le statut par défaut « à vérifier » bloque l'attribution."""
        beneficiaire = self._beneficiaire()
        self.assertFalse(beneficiaire.eligible)
        self.assertIn('RG-009', beneficiaire.eligibility_blocker)
        with self.assertRaises(ValidationError):
            beneficiaire.check_eligibility()

    def test_verification_exige_une_piece(self):
        beneficiaire = self._beneficiaire(identity_document_number=False)
        with self.assertRaises(ValidationError):
            beneficiaire.action_verify_beneficiary()

    def test_verifie_eligible(self):
        beneficiaire = self._beneficiaire()
        beneficiaire.action_verify_beneficiary()
        self.assertTrue(beneficiaire.eligible)
        self.assertFalse(beneficiaire.eligibility_blocker)

    def test_suspendu_non_eligible(self):
        beneficiaire = self._beneficiaire()
        beneficiaire.action_verify_beneficiary()
        beneficiaire.action_suspend_beneficiary()
        self.assertFalse(beneficiaire.eligible)

    def test_plafond_de_categorie(self):
        """RG-010 : au plafond, plus aucune attribution n'est possible."""
        beneficiaire = self._beneficiaire()
        beneficiaire.action_verify_beneficiary()
        self._equipement(beneficiaire)
        beneficiaire.invalidate_recordset()

        self.assertEqual(beneficiaire.ansut_equipment_count, 1)
        self.assertFalse(beneficiaire.eligible)
        self.assertIn('RG-010', beneficiaire.eligibility_blocker)

    def test_equipements_sortis_ne_comptent_plus(self):
        """Un équipement perdu ou hors service libère la place sous le plafond."""
        beneficiaire = self._beneficiaire()
        beneficiaire.action_verify_beneficiary()
        equipement = self._equipement(beneficiaire)
        beneficiaire.invalidate_recordset()
        self.assertFalse(beneficiaire.eligible)

        equipement.ansut_condition = 'lost'
        beneficiaire.invalidate_recordset()
        self.assertEqual(beneficiaire.ansut_equipment_count, 0)
        self.assertTrue(beneficiaire.eligible)

    def test_plafond_zero_sans_limite(self):
        beneficiaire = self._beneficiaire(self.categorie_libre)
        beneficiaire.action_verify_beneficiary()
        for indice in range(3):
            self._equipement(beneficiaire, suffixe=str(indice))
        beneficiaire.invalidate_recordset()
        self.assertTrue(beneficiaire.eligible)
