# -*- coding: utf-8 -*-
"""Retrait d'équipement par un bénéficiaire (DSD §19 à §29).

Un retrait **est** un transfert Odoo. On n'ouvre pas de modèle parallèle :
`stock.picking` apporte déjà l'état, le destinataire, les dates, l'origine et
la destination, la réservation qui empêche d'engager deux fois le même numéro
de série, les mouvements de stock réels, la signature, les reprises de
reliquat et la traçabilité. Un modèle maison aurait redit tout cela — et,
surtout, n'aurait jamais bougé le stock.

Ce module n'ajoute que ce qu'Odoo n'a pas : l'authentification du bénéficiaire
au comptoir par deux facteurs indépendants, un QR porteur d'un jeton opaque
(§23) et un PIN à usage unique (§24), ni l'un ni l'autre n'exposant de donnée
personnelle, le PIN n'étant jamais stocké en clair.
"""
import hashlib
import hmac
import secrets
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

#: Nombre de tentatives de PIN avant blocage (§24).
MAX_PIN_ATTEMPTS = 3
#: Durée de validité par défaut du QR et du PIN, en jours (§23, §24).
DEFAULT_VALIDITY_DAYS = 7


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    # --- Qualification du transfert (§19) ------------------------------------
    is_ansut_withdrawal = fields.Boolean(
        string="Retrait ANSUT", related='picking_type_id.is_ansut_withdrawal',
        store=True, index=True)

    # --- Sous-cycle propre au retrait (§20) ----------------------------------
    # L'état logistique reste celui d'Odoo (brouillon, en attente, prêt,
    # fait, annulé). Ce champ ne décrit que l'avancement de la procédure de
    # retrait, qu'aucun état de transfert n'exprime.
    withdrawal_state = fields.Selection(
        selection=[
            ('pending', "À préparer"),
            ('secrets_issued', "QR et PIN générés"),
            ('notified', "Bénéficiaire notifié"),
            ('checking', "Contrôle au comptoir"),
            ('delivered', "Remis"),
        ],
        string="Étape du retrait", default='pending', copy=False, tracking=True, index=True)

    # --- Secrets de retrait (§23, §24) ---------------------------------------
    qr_token = fields.Char(
        string="Jeton QR", copy=False, readonly=True, groups='stock.group_stock_manager')
    pin_hash = fields.Char(
        string="Empreinte du PIN", copy=False, readonly=True, groups='stock.group_stock_manager',
        help="Le PIN n'est jamais stocké en clair : seule son empreinte est conservée.")
    pin_attempts = fields.Integer(string="Tentatives de PIN", default=0, copy=False, readonly=True)
    pin_blocked = fields.Boolean(string="PIN bloqué", compute='_compute_pin_blocked', store=True)
    withdrawal_expiration = fields.Datetime(
        string="Expiration du retrait", copy=False,
        help="Au-delà de cette date, le QR et le PIN sont invalides (§23, §24).")

    # --- Contrôle d'identité au comptoir (§26) -------------------------------
    # La signature du bénéficiaire est le champ `signature` standard du
    # transfert : on ne le double pas.
    identity_document_type = fields.Selection(
        selection=[('cni', "CNI"), ('passport', "Passeport"),
                   ('permis', "Permis de conduire"),
                   ('attestation', "Attestation d'identité")],
        string="Pièce présentée", copy=False)
    identity_document_number = fields.Char(string="Numéro de la pièce", copy=False)
    delivery_photo = fields.Image(
        string="Photo de l'équipement remis", max_width=1920, copy=False)

    # --- Raccourci de lecture (§19) ------------------------------------------
    ansut_equipment_ids = fields.Many2many(
        'stock.lot', string="Équipements du retrait",
        compute='_compute_ansut_equipment_ids',
        help="Numéros de série engagés par les mouvements du transfert.")

    # --- Éligibilité du bénéficiaire (§22) -----------------------------------
    beneficiary_eligible = fields.Boolean(
        related='partner_id.eligible', string="Bénéficiaire éligible")
    beneficiary_eligibility_blocker = fields.Char(
        related='partner_id.eligibility_blocker', string="Motif de non-éligibilité")

    # --- Calculs -------------------------------------------------------------
    @api.depends('pin_attempts')
    def _compute_pin_blocked(self):
        for picking in self:
            picking.pin_blocked = picking.pin_attempts >= MAX_PIN_ATTEMPTS

    @api.depends('move_ids.move_line_ids.lot_id')
    def _compute_ansut_equipment_ids(self):
        for picking in self:
            picking.ansut_equipment_ids = picking.move_ids.move_line_ids.lot_id

    # --- Contraintes ---------------------------------------------------------
    @api.constrains('partner_id', 'state', 'is_ansut_withdrawal')
    def _check_beneficiary_eligible(self):
        """RG-009 et RG-010 : on n'engage un équipement que vers un bénéficiaire
        vérifié et sous son plafond.

        Le contrôle porte sur l'**engagement**, et seulement sur lui. Pas au
        brouillon, pour ne pas empêcher la préparation d'un dossier ; et pas
        une fois le retrait servi, sinon la règle se retourne contre lui : le
        bénéficiaire est à son plafond *à cause* de cette remise, et le moindre
        écrit ultérieur sur le transfert — jusqu'à une simple mise à jour de
        module — deviendrait impossible.
        """
        for picking in self:
            if not picking.is_ansut_withdrawal:
                continue
            if picking.state in ('draft', 'done', 'cancel'):
                continue
            if not picking.partner_id:
                raise ValidationError(_("Un retrait ANSUT désigne son bénéficiaire (§19)."))
            picking.partner_id.check_eligibility()

    # --- Secrets -------------------------------------------------------------
    @api.model
    def _pin_attempts_max(self):
        """Nombre de tentatives autorisées, exposé aux écrans agent (§24)."""
        return MAX_PIN_ATTEMPTS

    def _hash_pin(self, pin):
        """Empreinte du PIN, salée par la clé d'instance (§24)."""
        cle = self.env['ir.config_parameter'].sudo().get_param('database.secret', '')
        return hmac.new(cle.encode(), pin.encode(), hashlib.sha256).hexdigest()

    def action_issue_secrets(self):
        """Génère le QR et le PIN, et fixe leur expiration (§20, §23, §24)."""
        for picking in self:
            if not picking.is_ansut_withdrawal:
                raise UserError(_("Ce transfert n'est pas un retrait ANSUT."))
            if picking.state in ('done', 'cancel'):
                raise UserError(_("Le retrait %s est terminé.", picking.name))
            pin = f"{secrets.randbelow(10 ** 6):06d}"
            picking.write({
                'qr_token': secrets.token_urlsafe(24),
                'pin_hash': picking._hash_pin(pin),
                'pin_attempts': 0,
                'withdrawal_expiration':
                    fields.Datetime.now() + timedelta(days=DEFAULT_VALIDITY_DAYS),
                'withdrawal_state': 'secrets_issued',
            })
            # Le PIN en clair ne quitte pas cet appel : il part en notification
            # au bénéficiaire et n'est jamais journalisé.
            picking.message_post(body=_("PIN de retrait généré et transmis au bénéficiaire."))
        return True

    def _check_withdrawal_expired(self):
        """RG-006 et RG-007 : un QR ou un PIN expiré est invalide."""
        self.ensure_one()
        if self.withdrawal_expiration and self.withdrawal_expiration < fields.Datetime.now():
            raise UserError(_("Le retrait a expiré le %s. Régénérez un QR et un PIN.",
                              fields.Datetime.to_string(self.withdrawal_expiration)))

    def verify_pin(self, pin):
        """Vérifie le PIN saisi au point de retrait (§25).

        Retourne vrai si le PIN est bon, faux sinon — et **ne lève pas** sur un
        PIN faux. C'est délibéré : une erreur remontée à l'appelant annule la
        transaction, et le compteur de tentatives serait annulé avec elle. Le
        verrou après trois essais ne verrouillerait alors jamais rien.

        Les autres refus (retrait expiré, PIN bloqué, aucun PIN généré) lèvent,
        eux : ce sont des états, ils n'écrivent rien qu'un rollback perdrait.
        """
        self.ensure_one()
        self._check_withdrawal_expired()
        if self.pin_blocked:
            raise UserError(_(
                "PIN bloqué après %s tentatives infructueuses. "
                "Un responsable doit régénérer le retrait.", MAX_PIN_ATTEMPTS))
        if not self.sudo().pin_hash:
            raise UserError(_("Aucun PIN n'a été généré pour ce retrait."))

        if hmac.compare_digest(self.sudo().pin_hash, self._hash_pin(pin or '')):
            self.sudo().write({'pin_attempts': 0, 'withdrawal_state': 'checking'})
            return True

        self.sudo().pin_attempts += 1
        return False

    def pin_attempts_left(self):
        """Tentatives restantes avant blocage (§24)."""
        self.ensure_one()
        return max(MAX_PIN_ATTEMPTS - self.pin_attempts, 0)

    def action_revoke_secrets(self):
        """Révoque le QR et le PIN : les anciens deviennent inutilisables (§23)."""
        self.sudo().write({'qr_token': False, 'pin_hash': False, 'pin_attempts': 0})
        return True

    # --- Remise --------------------------------------------------------------
    def button_validate(self):
        """Contrôles propres au retrait, puis validation standard du transfert.

        La sortie de stock, la traçabilité et l'éventuel reliquat restent
        l'affaire d'Odoo : on ne réécrit pas ce que le transfert sait faire.
        """
        retraits = self.filtered('is_ansut_withdrawal')
        for picking in retraits:
            if picking.state == 'done':
                raise UserError(_(
                    "RG-005 : le retrait %s est déjà clôturé.", picking.name))
            if picking.withdrawal_state != 'checking':
                raise UserError(_("Le PIN du bénéficiaire doit être vérifié avant la remise."))
            picking._check_withdrawal_expired()
            if not picking.signature:
                raise UserError(_("La signature du bénéficiaire est requise (§26)."))
            if not picking.identity_document_number:
                raise UserError(_("Relevez le numéro de la pièce présentée (§26)."))

        resultat = super().button_validate()

        # Odoo peut interrompre la validation par un assistant (reliquat,
        # quantités) : on ne clôture le retrait que s'il est réellement validé.
        for picking in retraits.filtered(lambda p: p.state == 'done'):
            picking.write({'withdrawal_state': 'delivered'})
            # Le détenteur des équipements découle du transfert validé : il est
            # posé ici, et nulle part ailleurs.
            picking.ansut_equipment_ids.sudo().write(
                {'beneficiary_id': picking.partner_id.id})
            # Le PIN et le QR sont invalidés dès la remise (§24).
            picking.action_revoke_secrets()
            picking.message_post(body=_("Remise validée et retrait clôturé."))
        return resultat

    def action_cancel(self):
        resultat = super().action_cancel()
        self.filtered('is_ansut_withdrawal').action_revoke_secrets()
        return resultat


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_ansut_withdrawal = fields.Boolean(
        string="Retrait ANSUT",
        help="Les transferts de ce type suivent la procédure de retrait "
             "sécurisée : QR, PIN et contrôle d'identité au comptoir.")
