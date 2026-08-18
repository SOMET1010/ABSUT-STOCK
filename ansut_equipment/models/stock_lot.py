# -*- coding: utf-8 -*-
"""Référentiel équipement unitaire ANSUT (DSD §11 à §14, §33).

L'équipement individuel reste un `stock.lot` sérialisé : on étend le modèle
standard plutôt que d'en créer un parallèle, conformément à la matrice §74
qui classe « Séries » en standard Odoo avec extension.
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
    equipment_uid = fields.Char(
        string="Identifiant ANSUT", copy=False, index=True, readonly=True,
        help="Identifiant unique ANSUT, attribué automatiquement à la création.")
    serial_number = fields.Char(
        string="Numéro de série", related='name', store=True, readonly=False)
    imei = fields.Char(string="IMEI", copy=False, index=True)
    manufacturer_reference = fields.Char(string="Référence constructeur")
    asset_number = fields.Char(string="Numéro d'immobilisation", copy=False)

    # --- Retrait sécurisé (§23) ---------------------------------------------
    qr_token = fields.Char(
        string="Jeton QR", copy=False, readonly=True, groups='stock.group_stock_manager',
        help="Jeton opaque du QR code. N'expose aucune donnée personnelle.")

    # --- Cycle de vie (§14) --------------------------------------------------
    lifecycle_state = fields.Selection(
        selection=[
            ('new', "Nouveau"),
            ('received', "Reçu"),
            ('in_stock', "En stock"),
            ('reserved', "Réservé"),
            ('in_transit', "En transit"),
            ('available_pickup', "Disponible au retrait"),
            ('assigned', "Attribué"),
            ('delivered', "Remis"),
            ('after_sales', "SAV"),
            ('repair', "Réparation"),
            ('lost', "Perdu"),
            ('out_of_order', "Hors service"),
            ('scrapped', "Mis au rebut"),
        ],
        string="État du cycle de vie", default='new', required=True, tracking=True, index=True)

    # --- Dates et garantie (§12, §33) ---------------------------------------
    acquisition_date = fields.Date(string="Date d'acquisition")
    commissioning_date = fields.Date(string="Date de mise en service")
    warranty_start = fields.Date(string="Début de garantie")
    warranty_end = fields.Date(string="Fin de garantie")
    warranty_active = fields.Boolean(
        string="Garantie active", compute='_compute_warranty_active', store=True,
        help="Vrai tant que la date du jour est comprise dans la période de garantie.")

    # --- Affectation (§12, §22) ---------------------------------------------
    beneficiary_id = fields.Many2one(
        'res.partner', string="Bénéficiaire", copy=False, index=True, tracking=True)
    current_site_id = fields.Many2one('stock.warehouse', string="Site actuel", index=True)
    current_location_id = fields.Many2one('stock.location', string="Emplacement actuel")
    marking_type_id = fields.Many2one('ansut.equipment.marking', string="Type de marquage")

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

    # --- Contraintes ---------------------------------------------------------
    @api.constrains('warranty_start', 'warranty_end')
    def _check_warranty_period(self):
        for lot in self:
            if lot.warranty_start and lot.warranty_end and lot.warranty_end < lot.warranty_start:
                raise ValidationError(
                    _("La fin de garantie ne peut pas précéder son début."))

    @api.constrains('lifecycle_state', 'beneficiary_id')
    def _check_beneficiary_required(self):
        """RG-003 : un équipement attribué ou remis désigne son bénéficiaire."""
        for lot in self:
            if lot.lifecycle_state in ('assigned', 'delivered') and not lot.beneficiary_id:
                raise ValidationError(_(
                    "RG-003 : un équipement %s doit désigner son bénéficiaire.",
                    dict(self._fields['lifecycle_state'].selection)[lot.lifecycle_state]))

    # --- Création ------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('equipment_uid'):
                vals['equipment_uid'] = self.env['ir.sequence'].next_by_code(
                    'ansut.equipment.uid') or f"ANSUT-{secrets.token_hex(4).upper()}"
            if not vals.get('qr_token'):
                # Jeton opaque, non prédictible et révocable (§23).
                vals['qr_token'] = secrets.token_urlsafe(24)
        return super().create(vals_list)

    def action_revoke_qr_token(self):
        """Révoque le QR : le jeton précédent devient invalide (§23)."""
        for lot in self:
            lot.qr_token = secrets.token_urlsafe(24)
        return True
