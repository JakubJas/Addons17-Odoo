from odoo import models, _
from odoo.exceptions import UserError


class MailActivity(models.Model):

    _inherit = "mail.activity"
    
    def action_feedback(self, feedback=False):

        res = super().action_feedback(feedback)

        for activity in self:

            if activity.summary and "PPTO:" in activity.summary:

                lead = self.env["crm.lead"].browse(activity.res_id)

                # eliminar actividades de otros usuarios
                others = self.search([
                    ("res_id", "=", lead.id),
                    ("id", "!=", activity.id),
                    ("activity_type_id", "=", activity.activity_type_id.id),
                ])

                others.unlink()

                # asignar responsable del presupuesto
                lead.user_id = activity.user_id

        return res