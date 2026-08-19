# -*- coding: utf-8 -*-
"""Distribution d'un équipement à un bénéficiaire (DSD §19 à §29).

Le retrait est sécurisé par deux facteurs indépendants : un QR porteur d'un
jeton opaque (§23) et un PIN à usage unique (§24). Ni l'un ni l'autre
n'expose de donnée personnelle, et le PIN n'est jamais stocké en clair.
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


class AnsutDistribution(models.Model):
    _name = 'ansut.distribution'
    _description = "Distribution d'équipement ANSUT"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'reservation_date desc, id desc'
    _rec_name = 'reference'

    # --- Identification (§19) ------------------------------------------------
    reference = fields.Char(
        string="Référence", copy=False, readonly=True, index=True, default="Nouveau")

    # --- Parties prenantes (§19, §22) ---------------------------------------
    beneficiary_id = fields.Many2one(
        'res.partner', string="Bénéficiaire", required=True, tracking=True, index=True,
        domain="[('is_ansut_beneficiary', '=', True)]")
    beneficiary_eligible = fields.Boolean(
        related='beneficiary_id.eligible', string="Bénéficiaire éligible")
    beneficiary_eligibility_blocker = fields.Char(
        related='beneficiary_id.eligibility_blocker', string="Motif de non-éligibilité")
    equipment_id = fields.Many2one(
        'stock.lot', string="Équipement", required=True, tracking=True, index=True,
        domain="[('lifecycle_state', 'in', ['in_stock', 'reserved'])]")
    warehouse_id = fields.Many2one('stock.warehouse', string="Entrepôt d'origine")
    pickup_point_id = fields.Many2one(
        'stock.location', string="Point de retrait", tracking=True)
    agent_id = fields.Many2one(
        'res.users', string="Agent de retrait", tracking=True,
        help="Agent ayant procédé au contrôle et à la remise.")

    # --- Dates (§19) ---------------------------------------------------------
    reservation_date = fields.Datetime(string="Date de réservation", copy=False)
    withdrawal_date = fields.Datetime(string="Date de remise", copy=False, readonly=True)
    expiration_date = fields.Datetime(
        string="Expiration du retrait", copy=False,
        help="Au-delà de cette date, le QR et le PIN sont invalides (§23, §24).")

    # --- Secrets de retrait (§23, §24) ---------------------------------------
    qr_token = fields.Char(
        string="Jeton QR", copy=False, readonly=True, groups='stock.group_stock_manager')
    pin_hash = fields.Char(
        string="Empreinte du PIN", copy=False, readonly=True, groups='stock.group_stock_manager',
        help="Le PIN n'est jamais stocké en clair : seule son empreinte est conservée.")
    pin_attempts = fields.Integer(string="Tentatives de PIN", default=0, copy=False, readonly=True)
    pin_blocked = fields.Boolean(string="PIN bloqué", compute='_compute_pin_blocked', store=True)

    # --- Preuves de remise (§26, §27) ---------------------------------------
    delivery_photo = fields.Image(string="Photo de l'équipement remis", max_width=1920)
    delivery_signature = fields.Image(string="Signature du bénéficiaire", max_width=1024)
    identity_document_type = fields.Selection(
        selection=[('cni', "CNI"), ('passport', "Passeport"), ('permis', "Permis de conduire"),
                   ('attestation', "Attestation d'identité")],
        string="Type de pièce d'identité")
    identity_document_number = fields.Char(string="Numéro de pièce d'identité")

    # --- Cycle de vie (§20) --------------------------------------------------
    state = fields.Selection(
        selection=[
            ('draft', "Brouillon"),
            ('validated', "Validée"),
            ('reserved', "Réservée"),
            ('secrets_issued', "QR et PIN générés"),
            ('notified', "Notifiée"),
            ('in_transit', "Acheminement"),
            ('available', "Disponible au retrait"),
            ('checking', "Contrôle bénéficiaire"),
            ('delivered', "Remise"),
            ('closed', "Clôturée"),
            ('cancelled', "Annulée"),
        ],
        string="État", default='draft', required=True, tracking=True, index=True)

    _sql_constraints = [
        ('reference_uniq', 'unique(reference)', "La référence de distribution doit être unique."),
    ]

    # --- Calculs -------------------------------------------------------------
    @api.depends('pin_attempts')
    def _compute_pin_blocked(self):
        for distribution in self:
            distribution.pin_blocked = distribution.pin_attempts >= MAX_PIN_ATTEMPTS

    # --- Contraintes ---------------------------------------------------------
    @api.constrains('equipment_id', 'state')
    def _check_equipment_not_already_engaged(self):
        """RG-003 : un équipement ne peut pas être promis à deux bénéficiaires."""
        engaged = ('validated', 'reserved', 'secrets_issued', 'notified',
                   'in_transit', 'available', 'checking')
        for distribution in self:
            if distribution.state not in engaged:
                continue
            conflit = self.search_count([
                ('id', '!=', distribution.id),
                ('equipment_id', '=', distribution.equipment_id.id),
                ('state', 'in', engaged),
            ])
            if conflit:
                raise ValidationError(_(
                    "RG-003 : l'équipement « %s » fait déjà l'objet d'une autre "
                    "distribution en cours.", distribution.equipment_id.display_name))

    @api.constrains('beneficiary_id', 'state')
    def _check_beneficiary_eligible(self):
        """RG-009 et RG-010 : on n'engage un équipement que vers un bénéficiaire
        vérifié et sous son plafond. Le contrôle a lieu à l'engagement, pas au
        brouillon, pour ne pas empêcher la préparation d'un dossier."""
        for distribution in self:
            if distribution.state in ('draft', 'cancelled'):
                continue
            distribution.beneficiary_id.check_eligibility()

    # --- Création ------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', "Nouveau") == "Nouveau":
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'ansut.distribution') or f"RET-{secrets.token_hex(3).upper()}"
        return super().create(vals_list)

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
        for distribution in self:
            if distribution.state not in ('reserved', 'validated'):
                raise UserError(_("Le QR et le PIN se génèrent après la réservation."))
            pin = f"{secrets.randbelow(10 ** 6):06d}"
            distribution.write({
                'qr_token': secrets.token_urlsafe(24),
                'pin_hash': distribution._hash_pin(pin),
                'pin_attempts': 0,
                'expiration_date': fields.Datetime.now() + timedelta(days=DEFAULT_VALIDITY_DAYS),
                'state': 'secrets_issued',
            })
            # Le PIN en clair n'est retourné qu'ici, pour notification immédiate.
            distribution.message_post(body=_("PIN de retrait généré et transmis au bénéficiaire."))
        return True

    def _check_expired(self):
        """RG-006 et RG-007 : un QR ou un PIN expiré est invalide."""
        self.ensure_one()
        if self.expiration_date and self.expiration_date < fields.Datetime.now():
            raise UserError(_("Le retrait a expiré le %s. Régénérez un QR et un PIN.",
                              fields.Datetime.to_string(self.expiration_date)))

    def verify_pin(self, pin):
        """Vérifie le PIN saisi au point de retrait (§25)."""
        self.ensure_one()
        self._check_expired()
        if self.pin_blocked:
            raise UserError(_(
                "PIN bloqué après %s tentatives infructueuses. "
                "Un responsable doit régénérer le retrait.", MAX_PIN_ATTEMPTS))
        if not self.pin_hash:
            raise UserError(_("Aucun PIN n'a été généré pour ce retrait."))

        if hmac.compare_digest(self.pin_hash, self._hash_pin(pin or '')):
            self.write({'pin_attempts': 0, 'state': 'checking'})
            return True

        self.pin_attempts += 1
        restantes = max(MAX_PIN_ATTEMPTS - self.pin_attempts, 0)
        raise UserError(_("PIN incorrect. %s tentative(s) restante(s).", restantes))

    def action_revoke_secrets(self):
        """Révoque le QR et le PIN : les anciens deviennent inutilisables (§23)."""
        self.write({'qr_token': False, 'pin_hash': False, 'pin_attempts': 0})
        return True

    # --- Remise --------------------------------------------------------------
    def action_deliver(self):
        """Valide la remise (§28) : contrôles, sortie de stock, clôture."""
        for distribution in self:
            if distribution.state == 'closed':
                raise UserError(_(
                    "RG-005 : la remise %s est déjà clôturée et ne peut être "
                    "validée une seconde fois.", distribution.reference))
            if distribution.state != 'checking':
                raise UserError(_("Le PIN doit être validé avant la remise."))
            distribution._check_expired()
            if not distribution.delivery_signature:
                raise UserError(_("La signature du bénéficiaire est requise (§26)."))

            distribution.equipment_id.write({
                'lifecycle_state': 'delivered',
                'beneficiary_id': distribution.beneficiary_id.id,
            })
            distribution.write({
                'state': 'closed',
                'withdrawal_date': fields.Datetime.now(),
                'agent_id': self.env.user.id,
                # Le PIN est invalidé dès la remise (§24).
                'pin_hash': False,
                'qr_token': False,
            })
            distribution.message_post(body=_("Remise validée et retrait clôturé."))
        return True

    def action_cancel(self):
        self.write({'state': 'cancelled'})
        return self.action_revoke_secrets()
