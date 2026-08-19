# -*- coding: utf-8 -*-
"""Ordre de réparation d'un équipement ANSUT (DSD §31, §32, §33).

`repair.order` est communautaire et couvre déjà l'essentiel : pièces, états,
mouvements de stock, et même un indicateur `under_warranty`. Le seul manque est
qu'il faut le cocher à la main — alors que la garantie de l'équipement est une
donnée du parc. On le calcule, en le laissant surchargeable : un geste
commercial reste possible.
"""
from odoo import api, fields, models


class RepairOrder(models.Model):
    _inherit = 'repair.order'

    is_ansut_equipment = fields.Boolean(
        string="Équipement ANSUT", compute='_compute_is_ansut_equipment')

    # --- Garantie (§33) ------------------------------------------------------
    under_warranty = fields.Boolean(
        compute='_compute_under_warranty', store=True, readonly=False,
        help="Déduit de la garantie de l'équipement, et modifiable : un geste "
             "commercial hors garantie reste possible.")

    @api.depends('lot_id.equipment_uid')
    def _compute_is_ansut_equipment(self):
        for reparation in self:
            reparation.is_ansut_equipment = bool(reparation.lot_id.equipment_uid)

    @api.depends('lot_id.warranty_active')
    def _compute_under_warranty(self):
        for reparation in self:
            if reparation.lot_id.equipment_uid:
                reparation.under_warranty = reparation.lot_id.warranty_active
            else:
                reparation.under_warranty = reparation.under_warranty or False

    # --- Répercussion sur l'état de l'équipement (§14, §31) ------------------
    def action_repair_start(self):
        resultat = super().action_repair_start()
        self._ansut_set_condition('repair')
        return resultat

    def action_repair_end(self):
        resultat = super().action_repair_end()
        # Réparé : l'équipement peut retourner en service.
        self._ansut_set_condition('operational')
        return resultat

    def action_repair_cancel(self):
        resultat = super().action_repair_cancel()
        # Réparation abandonnée : l'équipement retourne au SAV, pas en service.
        self._ansut_set_condition('after_sales')
        return resultat

    def _ansut_set_condition(self, condition):
        for reparation in self.filtered('is_ansut_equipment'):
            reparation.lot_id.sudo().ansut_condition = condition
        return True
