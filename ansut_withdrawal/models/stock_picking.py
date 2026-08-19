# -*- coding: utf-8 -*-
"""Résolution d'un retrait depuis le QR présenté au comptoir (§25).

La recherche par jeton est le seul point d'entrée qui ne passe pas par un
formulaire authentifié : elle est traitée comme une opération sensible. Un
jeton vide ne remonte jamais rien, et l'erreur retournée ne distingue pas
« inconnu » de « déjà clôturé » — sans quoi le point de retrait deviendrait un
oracle à jetons.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    @api.model
    def find_by_qr_token(self, token):
        """Retourne le retrait correspondant au jeton, ou lève une erreur.

        Le jeton est porté par le QR du bénéficiaire (§23). Il ne suffit pas à
        déclencher la remise : le PIN reste exigé (§24).
        """
        token = (token or '').strip()
        if not token:
            raise UserError(_("Aucun QR code lu. Présentez le QR du bénéficiaire."))

        # sudo : l'agent n'a pas le droit de lire qr_token, réservé aux
        # responsables. La recherche reste bornée au seul jeton présenté.
        picking = self.sudo().search([
            ('qr_token', '=', token),
            ('is_ansut_withdrawal', '=', True),
        ], limit=1)

        if not picking or picking.state in ('done', 'cancel', 'draft'):
            raise UserError(_(
                "QR code non reconnu ou retrait déjà clôturé. "
                "Adressez le bénéficiaire à un responsable."))

        if picking.withdrawal_expiration and picking.withdrawal_expiration < fields.Datetime.now():
            raise UserError(_(
                "Le retrait %(reference)s a expiré le %(date)s. "
                "Un responsable doit régénérer le QR et le PIN.",
                reference=picking.name,
                date=fields.Datetime.to_string(picking.withdrawal_expiration)))

        # Rendu dans les droits de l'agent : la suite du parcours ne s'exécute
        # pas en sudo.
        return picking.sudo(False)

    def action_print_withdrawal_report(self):
        """Édite le PV de remise (§29), une fois la remise effective."""
        for picking in self:
            if picking.state != 'done' or not picking.is_ansut_withdrawal:
                raise UserError(_(
                    "Le PV de remise ne s'édite qu'après la remise effective "
                    "(retrait %s).", picking.name))
        return self.env.ref('ansut_withdrawal.action_report_withdrawal').report_action(self)
