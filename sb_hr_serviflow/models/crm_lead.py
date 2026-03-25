from odoo import models, fields


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def write(self, vals):

        res = super().write(vals)

        if "stage_id" in vals:

            stage = self.env["crm.stage"].browse(vals["stage_id"])

            if stage.name == "Solicitado Presupuesto Técnico":

                activity_type = self.env.ref(
                    "sb_hr_serviflow.mail_activity_type_budget_work",
                    raise_if_not_found=False
                )

                group = self.env.ref(
                    "sb_hr_serviflow.group_office_tech",
                    raise_if_not_found=False
                )

                if activity_type and group:

                    for lead in self:
                        for user in group.users:

                            self.env["mail.activity"].create({
                                "res_model_id": self.env["ir.model"]._get_id("crm.lead"),
                                "res_id": lead.id,
                                "user_id": user.id,
                                "activity_type_id": activity_type.id,
                                "summary": "Crear presupuesto técnico",
                                "note": "Se ha solicitado un presupuesto técnico",
                                "date_deadline": fields.Date.today(),
                            })

        return res