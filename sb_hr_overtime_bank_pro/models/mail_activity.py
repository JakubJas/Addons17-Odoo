from odoo import models


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    def action_feedback(self, feedback=False, attachment_ids=None, **kwargs):
        # Ignora attachment_ids y cualquier otro argumento extra
        return super().action_feedback(feedback=feedback)
    
    def action_feedback(self, feedback=False, attachment_ids=None, **kwargs):
        print("🔥 OVERRIDE MAIL.ACTIVITY FUNCIONANDO")
        return super().action_feedback(feedback=feedback)