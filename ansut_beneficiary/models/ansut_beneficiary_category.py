# -*- coding: utf-8 -*-
"""Catégories de bénéficiaires (DSD §22).

La catégorie n'est pas décorative : elle porte le plafond d'équipements que
peut détenir un bénéficiaire, que RG-010 fait respecter à l'attribution.
"""
from odoo import fields, models


class AnsutBeneficiaryCategory(models.Model):
    _name = 'ansut.beneficiary.category'
    _description = "Catégorie de bénéficiaire ANSUT"
    _order = 'sequence, name'

    name = fields.Char(string="Libellé", required=True, translate=True)
    code = fields.Char(string="Code", required=True)
    sequence = fields.Integer(string="Séquence", default=10)
    active = fields.Boolean(string="Actif", default=True)
    equipment_limit = fields.Integer(
        string="Plafond d'équipements", default=0,
        help="Nombre maximum d'équipements détenus simultanément. "
             "Zéro signifie « sans plafond ».")
    description = fields.Text(string="Description", translate=True)

    _sql_constraints = [
        ('code_uniq', 'unique(code)', "Le code de catégorie doit être unique."),
        ('limit_positive', 'CHECK(equipment_limit >= 0)',
         "Le plafond d'équipements ne peut pas être négatif."),
    ]
