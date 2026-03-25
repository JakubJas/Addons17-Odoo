# -*- coding: utf-8 -*-
from odoo import models, _
from odoo.exceptions import UserError


class MailActivity(models.Model):
    _inherit = "mail.activity"


    def action_feedback(self, feedback=False):
        """
        Se ejecuta cuando una actividad se marca como hecha.
        Aquí controlamos el flujo Serviflow.
        """

        res = super().action_feedback(feedback=feedback)

        for activity in self:

            if activity.res_model != "crm.lead":
                continue

            lead = self.env["crm.lead"].browse(activity.res_id)

            activity_type = activity.activity_type_id.xml_id

            # ---------------------------------------------------
            # ACTIVIDAD: ELABORAR PPTO
            # ---------------------------------------------------

            if activity_type == "serviflow_crm_budget.mail_activity_type_budget_work":

                lead.write({
                    "serviflow_budget_owner_id": activity.user_id.id,
                    "serviflow_budget_state": "done"
                })

                lead.action_serviflow_start_review()


            # ---------------------------------------------------
            # ACTIVIDAD: REVISIÓN
            # ---------------------------------------------------

            if activity_type == "serviflow_crm_budget.mail_activity_type_budget_review":

                validation = self.env["serviflow.budget.validation"].search([
                    ("lead_id", "=", lead.id),
                    ("validator_id", "=", activity.user_id.id)
                ], limit=1)

                if not validation:
                    raise UserError(_("No existe registro de validación."))

                # Si en el feedback pone OK
                if feedback and "ok" in feedback.lower():
                    validation.state = "approved"

                else:
                    validation.state = "rejected"
                    validation.comment = feedback

                lead.action_serviflow_recompute_review_state()


        return res