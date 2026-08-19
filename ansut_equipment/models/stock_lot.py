# -*- coding: utf-8 -*-
"""Référentiel équipement unitaire ANSUT (DSD §11 à §14, §33).

L'équipement individuel est un `stock.lot` sérialisé. On n'ajoute que ce
qu'Odoo ne sait pas dire de lui-même :

- Odoo connaît déjà **où** est l'équipement (`location_id`, `quant_ids`), **à
  qui** il a été livré (`last_delivery_partner_id`, `delivery_ids`) et **son
  numéro de série** (`name`). Rien de tout cela n'est redoublé ici.
- Odoo ne connaît pas l'identifiant ANSUT, l'IMEI, le marquage physique, la
  garantie, ni l'état d'un équipement sorti du circuit logistique (SAV, perdu,
  hors service). C'est l'objet de ce module.
"""
import secrets

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class AnsutEquipmentMarking(models.Model):
    """Type de marquage physique appliqué à l'équipement (§12 marking_type)."""

    _name = 'ansut.equipment.marking'
    _description = "Type de marquage d'équipement ANSUT"
    _order = 'sequence, name'

    name = fields.Char(string="Libellé", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Le code du type de marquage doit être unique."),
    ]


class StockLot(models.Model):
    _inherit = 'stock.lot'

    # --- Identification (§12, RG-001) ---------------------------------------
    # `name` porte déjà le numéro de série : on n'en fait pas une copie.
    equipment_uid = fields.Char(
        string="Identifiant ANSUT", copy=False, index=True, readonly=True,
        help="Identifiant unique ANSUT, attribué automatiquement à la création.")
    imei = fields.Char(string="IMEI", copy=False, index=True)
    manufacturer_reference = fields.Char(string="Référence constructeur")
    asset_number = fields.Char(string="Numéro d'immobilisation", copy=False)
    marking_type_id = fields.Many2one('ansut.equipment.marking', string="Type de marquage")

    # --- État hors circuit logistique (§14, §30 à §33) -----------------------
    # La position de l'équipement (en stock, réservé, en transit, livré) est
    # celle qu'Odoo calcule : elle n'est pas recopiée dans un champ maison qui
    # dériverait au premier mouvement fait hors de nos écrans. Ne subsistent
    # que les états qu'aucun mouvement de stock n'exprime.
    ansut_condition = fields.Selection(
        selection=[
            ('operational', "En service"),
            ('after_sales', "SAV"),
            ('repair', "En réparation"),
            ('lost', "Perdu"),
            ('out_of_order', "Hors service"),
        ],
        string="État de l'équipement", default='operational', required=True,
        tracking=True, index=True,
        help="État constaté de l'équipement, indépendant de sa position en "
             "stock. Un équipement perdu ou hors service ne compte plus dans "
             "le plafond de son bénéficiaire.")
    in_circulation = fields.Boolean(
        string="En circulation", compute='_compute_in_circulation', store=True,
        help="Faux dès que l'équipement sort du dispositif : perdu, hors "
             "service, ou mis au rebut.")

    # --- Dates et garantie (§12, §33) ---------------------------------------
    acquisition_date = fields.Date(string="Date d'acquisition")
    commissioning_date = fields.Date(string="Date de mise en service")
    warranty_start = fields.Date(string="Début de garantie")
    warranty_end = fields.Date(string="Fin de garantie")
    warranty_active = fields.Boolean(
        string="Garantie active", compute='_compute_warranty_active', store=True,
        help="Vrai tant que la date du jour est comprise dans la période de garantie.")

    # --- Détention (§22) -----------------------------------------------------
    # Odoo expose déjà `last_delivery_partner_id`, mais il est calculé à la
    # volée : impossible de filtrer ni de regrouper dessus. Le détenteur est
    # donc stocké — et posé par la validation du transfert, jamais saisi à la
    # main, pour qu'il ne puisse pas contredire les mouvements de stock.
    # Il n'est pas calculé : `delivery_ids` étant lui-même un champ calculé
    # non stocké, aucune dépendance ne peut s'y accrocher.
    beneficiary_id = fields.Many2one(
        'res.partner', string="Bénéficiaire", index=True, tracking=True,
        readonly=True, copy=False)

    _sql_constraints = [
        ('equipment_uid_uniq', 'unique(equipment_uid)',
         "RG-001 : l'identifiant ANSUT doit être unique."),
    ]

    # --- Calculs -------------------------------------------------------------
    @api.depends('warranty_start', 'warranty_end')
    def _compute_warranty_active(self):
        today = fields.Date.context_today(self)
        for lot in self:
            debut, fin = lot.warranty_start, lot.warranty_end
            lot.warranty_active = bool(fin and fin >= today and (not debut or debut <= today))

    @api.depends('ansut_condition')
    def _compute_in_circulation(self):
        for lot in self:
            lot.in_circulation = lot.ansut_condition not in ('lost', 'out_of_order')

    # --- Contraintes ---------------------------------------------------------
    @api.constrains('warranty_start', 'warranty_end')
    def _check_warranty_period(self):
        for lot in self:
            if lot.warranty_start and lot.warranty_end and lot.warranty_end < lot.warranty_start:
                raise ValidationError(
                    _("La fin de garantie ne peut pas précéder son début."))

    # --- Création ------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('equipment_uid'):
                vals['equipment_uid'] = self.env['ir.sequence'].next_by_code(
                    'ansut.equipment.uid') or f"ANSUT-{secrets.token_hex(4).upper()}"
        return super().create(vals_list)
