from odoo import models


class MailActivityMixin(models.AbstractModel):
    _inherit = 'mail.activity.mixin'

    def activity_feedback(self, act_type_xmlids, feedback=False, attachment_ids=None):
        Activity = self.env['mail.activity']

        for record in self:
            acts = Activity.search([
                ('res_id', '=', record.id),
                ('res_model', '=', record._name)
            ])

            # 🔥 FILTRAR SOLO LOS QUE EXISTEN
            acts = acts.exists()

            if acts:
                try:
                    acts.action_feedback(feedback=feedback)
                except Exception:
                    # Evita que reviente todo el flujo
                    continue

        return True