import logging

from odoo import models

_logger = logging.getLogger(__name__)


class MailActivityMixin(models.AbstractModel):
    _inherit = 'mail.activity.mixin'

    def activity_feedback(self, act_type_xmlids, feedback=False, attachment_ids=None):
        Activity = self.env['mail.activity']

        for record in self:
            acts = Activity.search([
                ('res_id', '=', record.id),
                ('res_model', '=', record._name)
            ])

            # Filtramos solo las que siguen existiendo.
            acts = acts.exists()

            if acts:
                try:
                    acts.action_feedback(feedback=feedback)
                except Exception:
                    # Evita que reviente todo el flujo, pero deja rastro.
                    _logger.exception(
                        "No se pudo completar la actividad para %s(%s)",
                        record._name,
                        record.id,
                    )
                    continue

        return True