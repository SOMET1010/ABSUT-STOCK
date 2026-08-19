# -*- coding: utf-8 -*-
"""Échange standard d'un équipement (DSD §34).

Le bénéficiaire repart avec un équipement de remplacement pendant que le sien
part en SAV. Le remplacement n'est pas une livraison ordinaire : il suit la
même procédure de retrait sécurisée que la remise initiale — QR et PIN — parce
que c'est le même geste, au même comptoir, avec le même besoin de preuve.

Le retour de l'équipement défaillant reste géré par `helpdesk_stock`, dont les
bons de retour existent déjà : ce module ne les réécrit pas.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AnsutExchangeWizard(models.TransientModel):
    _name = 'ansut.exchange.wizard'
    _description = "Échange standard d'un équipement ANSUT"

    ticket_id = fields.Many2one(
        'helpdesk.ticket', string="Ticket SAV", required=True, readonly=True)
    faulty_lot_id = fields.Many2one(
        related='ticket_id.lot_id', string="Équipement défaillant", readonly=True)
    beneficiary_id = fields.Many2one(
        related='ticket_id.lot_id.beneficiary_id', string="Bénéficiaire", readonly=True)
    product_id = fields.Many2one(
        related='ticket_id.lot_id.product_id', string="Modèle", readonly=True)
    warranty_active = fields.Boolean(
        related='ticket_id.lot_id.warranty_active', string="Sous garantie", readonly=True)

    replacement_lot_id = fields.Many2one(
        'stock.lot', string="Équipement de remplacement", required=True,
        domain="[('product_id', '=', product_id), ('beneficiary_id', '=', False),"
               " ('ansut_condition', '=', 'operational'), ('product_qty', '>', 0)]",
        help="Numéro de série disponible en stock, du même modèle, non attribué.")

    faulty_condition = fields.Selection(
        selection=[
            ('after_sales', "Part en SAV"),
            ('repair', "Part en réparation"),
            ('out_of_order', "Irréparable, hors service"),
            ('lost', "Perdu par le bénéficiaire"),
        ],
        string="Sort de l'équipement défaillant", default='after_sales', required=True)

    picking_type_id = fields.Many2one(
        'stock.picking.type', string="Type de retrait",
        default=lambda self: self.env.ref(
            'ansut_distribution.picking_type_ansut_withdrawal', raise_if_not_found=False),
        domain="[('is_ansut_withdrawal', '=', True)]", required=True)

    # --- Contrôles -----------------------------------------------------------
    @api.constrains('replacement_lot_id', 'faulty_lot_id')
    def _check_replacement_differs(self):
        for assistant in self:
            if assistant.replacement_lot_id == assistant.faulty_lot_id:
                raise UserError(_("L'équipement de remplacement doit être différent."))

    # --- Exécution -----------------------------------------------------------
    def action_exchange(self):
        """Crée le retrait du remplacement et bascule l'équipement défaillant."""
        self.ensure_one()
        if not self.beneficiary_id:
            raise UserError(_(
                "L'équipement %s n'a pas de détenteur enregistré : il n'y a rien "
                "à échanger.", self.faulty_lot_id.display_name))
        # RG-009 et RG-010 s'appliquent aussi à un échange : un bénéficiaire
        # suspendu ne repart pas avec du matériel.
        self.beneficiary_id.check_eligibility()

        retrait = self._creer_retrait_remplacement()
        retrait.action_issue_secrets()

        self.faulty_lot_id.sudo().ansut_condition = self.faulty_condition
        self.ticket_id.picking_ids = [fields.Command.link(retrait.id)]
        self.ticket_id.message_post(body=_(
            "Échange standard : retrait %(retrait)s créé pour l'équipement "
            "%(remplacement)s. L'équipement %(defaillant)s passe en « %(sort)s ».",
            retrait=retrait.name,
            remplacement=self.replacement_lot_id.display_name,
            defaillant=self.faulty_lot_id.display_name,
            sort=dict(self._fields['faulty_condition'].selection)[self.faulty_condition]))

        return {
            'type': 'ir.actions.act_window',
            'name': _("Retrait du remplacement"),
            'res_model': 'stock.picking',
            'res_id': retrait.id,
            'view_mode': 'form',
        }

    def _creer_retrait_remplacement(self):
        """Retrait ANSUT confirmé et réservé sur le numéro de série choisi."""
        self.ensure_one()
        source = self.picking_type_id.default_location_src_id
        destination = self.picking_type_id.default_location_dest_id

        retrait = self.env['stock.picking'].create({
            'picking_type_id': self.picking_type_id.id,
            'partner_id': self.beneficiary_id.id,
            'location_id': source.id,
            'location_dest_id': destination.id,
            'origin': self.ticket_id.display_name,
            'move_ids': [fields.Command.create({
                'name': self.product_id.display_name,
                'product_id': self.product_id.id,
                'product_uom_qty': 1,
                'product_uom': self.product_id.uom_id.id,
                'location_id': source.id,
                'location_dest_id': destination.id,
            })],
        })
        retrait.action_confirm()
        retrait.action_assign()

        # La réservation standard a pu retenir un autre numéro : on impose
        # celui que l'agent a choisi pour l'échange.
        lignes = retrait.move_ids.move_line_ids
        if not lignes:
            raise UserError(_(
                "Aucun stock disponible pour %s au point de retrait choisi.",
                self.product_id.display_name))
        lignes[1:].unlink()
        lignes[0].write({'lot_id': self.replacement_lot_id.id, 'quantity': 1})
        return retrait
