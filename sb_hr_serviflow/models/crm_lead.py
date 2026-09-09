from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CrmLead(models.Model):
    _inherit = "crm.lead"

    is_serviflow_budget_requested = fields.Boolean(
        string="Presupuesto técnico solicitado",
        compute="_compute_is_serviflow_budget_requested",
    )

    @api.depends("stage_id")
    def _compute_is_serviflow_budget_requested(self):
        for lead in self:
            lead.is_serviflow_budget_requested = (
                lead.stage_id.name == "Solicitado Presupuesto Técnico"
            )

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

    @api.model
    def get_serviflow_budget_stage_id(self):
        stage = self.env["crm.stage"].search([
            ("name", "=", "Solicitado Presupuesto Técnico")
        ], limit=1)

        return stage.id if stage else False

    def write(self, vals):
        # Si el cambio viene del wizard, permitimos el cambio sin bloquearlo
        if self.env.context.get("serviflow_from_wizard"):
            return super().write(vals)

        # Si alguien intenta mover manualmente a la etapa técnica,
        # por ahora bloqueamos para obligar a pasar por el wizard.
        if "stage_id" in vals:
            stage = self.env["crm.stage"].browse(vals["stage_id"])

            if stage.name == "Solicitado Presupuesto Técnico":
                raise UserError(
                    _(
                        "Para solicitar un presupuesto técnico debes usar "
                        "el botón 'Solicitar PPTO Técnico'."
                    )
                )

        return super().write(vals)