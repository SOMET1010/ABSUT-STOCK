# -*- coding: utf-8 -*-
"""Résolution d'un retrait depuis le QR présenté au point de retrait (§25).

La recherche par jeton est le seul point d'entrée non authentifié par un
formulaire : elle est donc traitée comme une opération sensible. Le jeton
n'est jamais comparé partiellement, un jeton vide ne remonte jamais rien, et
l'erreur retournée ne distingue pas « inconnu » de « déjà consommé » — sans
quoi le point de retrait deviendrait un oracle à jetons.
"""
from odoo import _, api, fields, models
from odoo.exceptions import UserError

#: États dans lesquels un retrait peut être présenté au point de retrait (§25).
PRESENTABLE_STATES = ('secrets_issued', 'notified', 'in_transit', 'available', 'checking')


class AnsutDistribution(models.Model):
    _inherit = 'ansut.distribution'

    @api.model
    def find_by_qr_token(self, token):
        """Retourne le retrait correspondant au jeton, ou lève une erreur.

        Le jeton est porté par le QR du bénéficiaire (§23). Il ne suffit pas à
        déclencher la remise : le PIN reste exigé (§24).
        """
        token = (token or '').strip()
        if not token:
            raise UserError(_("Aucun QR code lu. Présentez le QR du bénéficiaire."))

        # sudo : l'agent n'a pas le droit de lire le champ qr_token, réservé
        # aux responsables. La recherche reste bornée au seul jeton présenté.
        distribution = self.sudo().search([('qr_token', '=', token)], limit=1)

        if not distribution or distribution.state not in PRESENTABLE_STATES:
            raise UserError(_(
                "QR code non reconnu ou retrait déjà clôturé. "
                "Adressez le bénéficiaire à un responsable."))

        if distribution.expiration_date and distribution.expiration_date < fields.Datetime.now():
            raise UserError(_(
                "Le retrait %(reference)s a expiré le %(date)s. "
                "Un responsable doit régénérer le QR et le PIN.",
                reference=distribution.reference,
                date=fields.Datetime.to_string(distribution.expiration_date)))

        # L'enregistrement est rendu dans les droits de l'agent : la suite du
        # parcours ne s'exécute pas en sudo.
        return distribution.sudo(False)

    def action_print_withdrawal_report(self):
        """Édite le PV de remise (§29), une fois la remise effective."""
        for distribution in self:
            if distribution.state != 'closed':
                raise UserError(_(
                    "Le PV de remise ne s'édite qu'après la remise effective "
                    "(retrait %s).", distribution.reference))
        return self.env.ref('ansut_withdrawal.action_report_withdrawal').report_action(self)
