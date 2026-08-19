# -*- coding: utf-8 -*-
"""Bénéficiaire d'équipement ANSUT (DSD §22).

Un bénéficiaire reste un `res.partner` : on l'étend au lieu de créer un
référentiel parallèle, ce qui garde les adresses, les contacts et les
communications standard d'Odoo. Le qualificatif « bénéficiaire » est un
drapeau, l'éligibilité un état contrôlé.
"""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

#: États d'éligibilité d'un bénéficiaire (§22).
BENEFICIARY_STATES = [
    ('draft', "À vérifier"),
    ('verified', "Vérifié"),
    ('suspended', "Suspendu"),
    ('archived', "Sorti du dispositif"),
]

#: Seul un bénéficiaire vérifié peut recevoir un équipement (RG-009).
ELIGIBLE_STATES = ('verified',)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # --- Qualification (§22) -------------------------------------------------
    is_ansut_beneficiary = fields.Boolean(
        string="Bénéficiaire ANSUT", index=True,
        help="Coché, le contact peut recevoir des équipements du dispositif.")
    beneficiary_uid = fields.Char(
        string="Identifiant bénéficiaire", copy=False, index=True, readonly=True,
        help="Identifiant unique attribué à la qualification du bénéficiaire.")
    beneficiary_category_id = fields.Many2one(
        'ansut.beneficiary.category', string="Catégorie de bénéficiaire",
        tracking=True, ondelete='restrict')
    beneficiary_state = fields.Selection(
        selection=BENEFICIARY_STATES, string="Statut du bénéficiaire",
        default='draft', tracking=True, index=True)

    # --- Identité (§22, §26) -------------------------------------------------
    identity_document_type = fields.Selection(
        selection=[('cni', "CNI"), ('passport', "Passeport"),
                   ('permis', "Permis de conduire"),
                   ('attestation', "Attestation d'identité")],
        string="Type de pièce d'identité")
    identity_document_number = fields.Char(
        string="Numéro de pièce d'identité", copy=False,
        help="Référence de la pièce présentée à la qualification. "
             "La pièce présentée au retrait est enregistrée sur la distribution.")

    # --- Équipements détenus (§12, §22) --------------------------------------
    ansut_equipment_ids = fields.One2many(
        'stock.lot', 'beneficiary_id', string="Équipements détenus")
    ansut_equipment_count = fields.Integer(
        string="Équipements détenus", compute='_compute_ansut_equipment_count')
    eligible = fields.Boolean(
        string="Éligible à une attribution", compute='_compute_eligible',
        help="Vrai si le contact est un bénéficiaire vérifié, sous son plafond "
             "d'équipements.")
    eligibility_blocker = fields.Char(
        string="Motif de non-éligibilité", compute='_compute_eligible')

    _sql_constraints = [
        ('beneficiary_uid_uniq', 'unique(beneficiary_uid)',
         "L'identifiant bénéficiaire doit être unique."),
    ]

    # --- Calculs -------------------------------------------------------------
    @api.depends('ansut_equipment_ids')
    def _compute_ansut_equipment_count(self):
        # Les équipements sortis du dispositif ne comptent plus dans le plafond.
        comptes = dict(self.env['stock.lot']._read_group(
            [('beneficiary_id', 'in', self.ids),
             ('lifecycle_state', 'not in', ('scrapped', 'lost', 'out_of_order'))],
            groupby=['beneficiary_id'], aggregates=['__count'],
        ))
        for partner in self:
            partner.ansut_equipment_count = comptes.get(partner, 0)

    @api.depends('is_ansut_beneficiary', 'beneficiary_state',
                 'beneficiary_category_id.equipment_limit', 'ansut_equipment_count')
    def _compute_eligible(self):
        for partner in self:
            blocage = partner._eligibility_blocker()
            partner.eligibility_blocker = blocage
            partner.eligible = not blocage

    def _eligibility_blocker(self):
        """Motif empêchant une attribution, ou chaîne vide (RG-009, RG-010)."""
        self.ensure_one()
        if not self.is_ansut_beneficiary:
            return _("Ce contact n'est pas qualifié comme bénéficiaire ANSUT.")
        if self.beneficiary_state not in ELIGIBLE_STATES:
            libelles = dict(BENEFICIARY_STATES)
            return _("RG-009 : le bénéficiaire est « %s » et doit être vérifié.",
                     libelles.get(self.beneficiary_state, self.beneficiary_state))
        plafond = self.beneficiary_category_id.equipment_limit
        if plafond and self.ansut_equipment_count >= plafond:
            return _("RG-010 : plafond atteint pour la catégorie « %(categorie)s » "
                     "(%(detenus)s équipement(s) sur %(plafond)s).",
                     categorie=self.beneficiary_category_id.display_name,
                     detenus=self.ansut_equipment_count, plafond=plafond)
        return ""

    def check_eligibility(self):
        """Lève une erreur explicite si le bénéficiaire ne peut rien recevoir."""
        for partner in self:
            blocage = partner._eligibility_blocker()
            if blocage:
                raise ValidationError(_("%(nom)s : %(motif)s",
                                        nom=partner.display_name, motif=blocage))
        return True

    # --- Contraintes ---------------------------------------------------------
    @api.constrains('is_ansut_beneficiary', 'beneficiary_category_id')
    def _check_category_required(self):
        for partner in self:
            if partner.is_ansut_beneficiary and not partner.beneficiary_category_id:
                raise ValidationError(_(
                    "Un bénéficiaire ANSUT doit être rattaché à une catégorie (§22)."))

    # --- Attribution de l'identifiant ---------------------------------------
    def _assign_beneficiary_uid(self):
        """Attribue l'identifiant à la qualification, jamais avant."""
        for partner in self.filtered(
                lambda p: p.is_ansut_beneficiary and not p.beneficiary_uid):
            partner.beneficiary_uid = self.env['ir.sequence'].next_by_code(
                'ansut.beneficiary') or f"BEN-{partner.id:06d}"

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._assign_beneficiary_uid()
        return partners

    def write(self, vals):
        resultat = super().write(vals)
        if vals.get('is_ansut_beneficiary'):
            self._assign_beneficiary_uid()
        return resultat

    # --- Transitions ---------------------------------------------------------
    def action_verify_beneficiary(self):
        for partner in self:
            if not partner.identity_document_number:
                raise ValidationError(_(
                    "La pièce d'identité est requise pour vérifier « %s » (§22).",
                    partner.display_name))
        return self.write({'beneficiary_state': 'verified'})

    def action_suspend_beneficiary(self):
        return self.write({'beneficiary_state': 'suspended'})

    def action_reset_beneficiary(self):
        return self.write({'beneficiary_state': 'draft'})

    # --- Navigation ----------------------------------------------------------
    def action_open_ansut_equipment(self):
        """Ouvre les équipements détenus par le bénéficiaire (§22)."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Équipements de %s", self.display_name),
            'res_model': 'stock.lot',
            'view_mode': 'tree,form',
            'domain': [('beneficiary_id', '=', self.id)],
            'context': {'default_beneficiary_id': self.id},
        }
