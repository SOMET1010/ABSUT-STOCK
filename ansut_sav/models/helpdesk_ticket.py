# -*- coding: utf-8 -*-
"""SAV d'un équipement ANSUT (DSD §30 à §34).

Le ticket est un `helpdesk.ticket` standard. `helpdesk_stock` lui donne déjà le
numéro de série et les bons de retour, `helpdesk_repair` le lien vers les
ordres de réparation : rien de tout cela n'est réécrit ici.

N'est ajouté que ce qu'Odoo ne sait pas : l'état de garantie de l'équipement au
moment du ticket, la cohérence entre le demandeur et le détenteur déclaré, et
la répercussion du SAV sur l'état de l'équipement.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class HelpdeskTicket(models.Model):
    _inherit = 'helpdesk.ticket'

    # --- Rattachement au parc ANSUT (§30) ------------------------------------
    # `lot_id` vient de helpdesk_stock : on s'y accroche, on ne le double pas.
    equipment_uid = fields.Char(
        related='lot_id.equipment_uid', string="Identifiant ANSUT", store=True, index=True)
    is_ansut_equipment = fields.Boolean(
        string="Équipement ANSUT", compute='_compute_is_ansut_equipment', store=True)
    equipment_condition = fields.Selection(
        related='lot_id.ansut_condition', string="État de l'équipement", readonly=True)

    # --- Garantie (§33) ------------------------------------------------------
    equipment_warranty_active = fields.Boolean(
        related='lot_id.warranty_active', string="Sous garantie", store=True)
    equipment_warranty_end = fields.Date(
        related='lot_id.warranty_end', string="Fin de garantie")

    # --- Détenteur déclaré (§22, §30) ----------------------------------------
    equipment_beneficiary_id = fields.Many2one(
        related='lot_id.beneficiary_id', string="Détenteur déclaré")
    beneficiary_mismatch = fields.Boolean(
        string="Demandeur différent du détenteur",
        compute='_compute_beneficiary_mismatch',
        help="Le ticket est ouvert par quelqu'un d'autre que le détenteur "
             "enregistré de l'équipement. À vérifier avant toute prise en charge.")

    # --- Calculs -------------------------------------------------------------
    @api.depends('lot_id.equipment_uid')
    def _compute_is_ansut_equipment(self):
        for ticket in self:
            ticket.is_ansut_equipment = bool(ticket.lot_id.equipment_uid)

    @api.depends('partner_id', 'lot_id.beneficiary_id')
    def _compute_beneficiary_mismatch(self):
        for ticket in self:
            detenteur = ticket.lot_id.beneficiary_id
            ticket.beneficiary_mismatch = bool(
                detenteur and ticket.partner_id and detenteur != ticket.partner_id)

    # --- Prise en charge (§30) -----------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        tickets = super().create(vals_list)
        # Ouvrir un ticket sur un équipement du parc, c'est le déclarer en SAV :
        # l'état ne doit pas dépendre d'un clic supplémentaire qu'on oublie.
        tickets._ansut_set_condition('after_sales', seulement_si=('operational',))
        return tickets

    def _ansut_set_condition(self, condition, seulement_si=None):
        """Passe l'équipement dans l'état demandé, sans écraser un état plus grave."""
        for ticket in self.filtered('is_ansut_equipment'):
            actuel = ticket.lot_id.ansut_condition
            if seulement_si and actuel not in seulement_si:
                continue
            ticket.lot_id.sudo().ansut_condition = condition
        return True

    def action_ansut_return_to_service(self):
        """Clôt le SAV : l'équipement retourne en service (§30)."""
        self._require_ansut_equipment()
        return self._ansut_set_condition('operational')

    def action_ansut_declare_out_of_order(self):
        """Équipement irréparable : il sort du parc en circulation (§32)."""
        self._require_ansut_equipment()
        return self._ansut_set_condition('out_of_order')

    def action_ansut_declare_lost(self):
        """Équipement perdu par le bénéficiaire (§32)."""
        self._require_ansut_equipment()
        return self._ansut_set_condition('lost')

    def action_ansut_standard_exchange(self):
        """Ouvre l'assistant d'échange standard (§34)."""
        self.ensure_one()
        self._require_ansut_equipment()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Échange standard"),
            'res_model': 'ansut.exchange.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_ticket_id': self.id},
        }

    def _require_ansut_equipment(self):
        for ticket in self:
            if not ticket.is_ansut_equipment:
                raise UserError(_(
                    "Le ticket %s ne désigne aucun équipement du parc ANSUT.", ticket.display_name))
        return True
