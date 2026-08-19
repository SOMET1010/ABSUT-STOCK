# -*- coding: utf-8 -*-
"""Écran agent du point de retrait (DSD §25 à §28).

Le parcours suit quatre temps, dans cet ordre et sans raccourci possible :
scanner le QR, saisir le PIN, contrôler l'identité, remettre l'équipement.
L'assistant est transitoire : ni le PIN ni les données d'identité n'y
survivent à la session. Les preuves, elles, sont écrites sur le transfert,
qui est l'enregistrement d'audit.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: Étapes du parcours agent (§25).
WITHDRAWAL_STEPS = [
    ('scan', "Scanner le QR code"),
    ('pin', "Saisir le PIN"),
    ('check', "Contrôler et remettre"),
    ('done', "Remise effectuée"),
]


class AnsutWithdrawalWizard(models.TransientModel):
    _name = 'ansut.withdrawal.wizard'
    _description = "Retrait au point de retrait ANSUT"

    step = fields.Selection(
        selection=WITHDRAWAL_STEPS, string="Étape", default='scan', required=True)

    # --- Étape 1 : lecture du QR (§23, §25) ----------------------------------
    qr_token = fields.Char(
        string="QR code",
        help="Champ alimenté par la douchette ou le lecteur de la tablette.")
    picking_id = fields.Many2one(
        'stock.picking', string="Retrait", readonly=True)

    beneficiary_id = fields.Many2one(
        related='picking_id.partner_id', string="Bénéficiaire", readonly=True)
    equipment_ids = fields.Many2many(
        related='picking_id.ansut_equipment_ids', string="Équipements", readonly=True)
    reference = fields.Char(related='picking_id.name', string="Référence", readonly=True)
    expiration_date = fields.Datetime(
        related='picking_id.withdrawal_expiration', string="Expiration", readonly=True)

    # --- Étape 2 : PIN (§24) -------------------------------------------------
    # Le PIN n'est ni stocké ni journalisé : il ne vit que le temps de l'appel.
    pin = fields.Char(string="PIN à 6 chiffres")
    pin_attempts_left = fields.Integer(
        string="Tentatives restantes", compute='_compute_pin_attempts_left')
    pin_error = fields.Char(
        string="Erreur de saisie", readonly=True,
        help="Un PIN faux est signalé ici et non par une erreur : une erreur "
             "annulerait la transaction, et le compteur de tentatives avec elle.")

    # --- Étape 3 : contrôle et preuves (§26, §27) ----------------------------
    # Les preuves sont saisies ici puis reportées sur le transfert, qui reste
    # l'enregistrement d'audit.
    identity_document_type = fields.Selection(
        selection=[('cni', "CNI"), ('passport', "Passeport"),
                   ('permis', "Permis de conduire"),
                   ('attestation', "Attestation d'identité")],
        string="Pièce présentée")
    identity_document_number = fields.Char(string="Numéro de la pièce")
    delivery_photo = fields.Image(string="Photo de l'équipement remis", max_width=1920)
    delivery_signature = fields.Image(string="Signature du bénéficiaire", max_width=1024)

    # --- Calculs -------------------------------------------------------------
    @api.depends('picking_id.pin_attempts')
    def _compute_pin_attempts_left(self):
        maximum = self.env['stock.picking']._pin_attempts_max()
        for assistant in self:
            engagees = assistant.picking_id.pin_attempts or 0
            assistant.pin_attempts_left = max(maximum - engagees, 0)

    # --- Étape 1 -------------------------------------------------------------
    def action_scan(self):
        """Résout le QR présenté et passe à la saisie du PIN (§25)."""
        self.ensure_one()
        picking = self.env['stock.picking'].find_by_qr_token(self.qr_token)
        self.write({
            'picking_id': picking.id,
            # Le jeton lu ne reste pas dans l'assistant une fois résolu.
            'qr_token': False,
            'step': 'pin',
        })
        return self._reopen()

    # --- Étape 2 -------------------------------------------------------------
    def action_verify_pin(self):
        """Vérifie le PIN saisi ; l'échec est compté par le transfert (§24)."""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Scannez d'abord le QR code du bénéficiaire."))

        if not self.picking_id.verify_pin(self.pin):
            restantes = self.picking_id.pin_attempts_left()
            self.write({
                'pin': False,
                'pin_error': _("PIN incorrect. %s tentative(s) restante(s).", restantes),
            })
            return self._reopen()

        self.write({
            'pin': False,
            'pin_error': False,
            'step': 'check',
            'identity_document_type': self.beneficiary_id.identity_document_type,
        })
        return self._reopen()

    # --- Étape 3 -------------------------------------------------------------
    def action_deliver(self):
        """Reporte les preuves sur le transfert et valide la remise (§28)."""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_("Scannez d'abord le QR code du bénéficiaire."))
        if not self.identity_document_number:
            raise UserError(_("Relevez le numéro de la pièce présentée (§26)."))
        if not self.delivery_signature:
            raise UserError(_("La signature du bénéficiaire est requise (§26)."))

        self.picking_id.write({
            'identity_document_type': self.identity_document_type,
            'identity_document_number': self.identity_document_number,
            'delivery_photo': self.delivery_photo,
            # `signature` est le champ standard du transfert : on n'en ouvre
            # pas un second.
            'signature': self.delivery_signature,
        })
        # La sortie de stock, la traçabilité et le reliquat éventuel restent
        # l'affaire d'Odoo.
        self.picking_id.button_validate()
        self.write({'step': 'done'})
        return self._reopen()

    # --- Étape 4 -------------------------------------------------------------
    def action_print_report(self):
        """Édite le PV de remise du retrait qui vient d'être clôturé (§29)."""
        self.ensure_one()
        return self.picking_id.action_print_withdrawal_report()

    def action_next_beneficiary(self):
        """Réarme l'écran pour le bénéficiaire suivant, sans rien conserver."""
        self.ensure_one()
        suivant = self.create({})
        return suivant._reopen()

    # --- Affichage -----------------------------------------------------------
    def _reopen(self):
        """Rouvre l'assistant sur son étape courante."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Point de retrait"),
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
