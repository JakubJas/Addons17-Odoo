from odoo import models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def action_feedback(self, feedback=False, attachment_ids=None, **kwargs):
        # Ignora cualquier argumento extra no soportado por el core,
        # pero conserva attachment_ids para no perder adjuntos.
        return super().action_feedback(
            feedback=feedback,
            attachment_ids=attachment_ids,
        )