from odoo import models


class CrmLead(models.Model):
    _inherit = "crm.lead"

    def write(self, vals):
        res = super().write(vals)
        
        if self.env.context.get("serviflow_from_wizard"):
            return res

        if "stage_id" not in vals:
            return res

        target_stage = self.env["crm.stage"].browse(vals["stage_id"])

        if target_stage.name != "Solicitado Presupuesto Técnico":
            return res

        for lead in self:
            existing = self.env["serviflow.task"].search_count([
                ("opportunity_id", "=", lead.id),
                ("state", "in", ["pending", "accepted"]),
            ])

            if existing:
                continue

            task = self.env["serviflow.task"].create({
                "name": f"PPTO - {lead.name}",
                "opportunity_id": lead.id,
                "task_type": "budget",
                "note": f"Solicitud creada automáticamente desde CRM para {lead.name}.",
            })

            task._create_group_activities()

        return res
    
    def action_open_serviflow_budget_wizard(self):
        self.ensure_one()

        return {
            "type": "ir.actions.act_window",
            "name": "Solicitar Presupuesto Técnico",
            "res_model": "serviflow.request.budget.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_opportunity_id": self.id,
            },
        }