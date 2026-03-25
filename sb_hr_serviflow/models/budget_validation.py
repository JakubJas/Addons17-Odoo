from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class ServiflowBudgetValidation(models.Model):
    _name = "serviflow.budget.validation"
    _description = "Serviflow Budget Validation"
    _order = "create_date desc"

    lead_id = fields.Many2one(
        "crm.lead",
        string="Oportunidad",
        required=True,
        ondelete="cascade",
        index=True,
    )
    validator_id = fields.Many2one(
        "res.users",
        string="Validador",
        required=True,
        index=True,
    )
    state = fields.Selection(
        [
            ("pending", "Pendiente"),
            ("approved", "Aprobado"),
            ("rejected", "Rechazado"),
        ],
        string="Estado",
        default="pending",
        required=True,
        index=True,
    )
    comment = fields.Text(string="Comentario")

    _sql_constraints = [
        ("uniq_lead_validator", "unique(lead_id, validator_id)", "Este validador ya tiene revisión para esta oportunidad."),
    ]

    @api.constrains("state", "comment")
    def _check_comment_if_rejected(self):
        for rec in self:
            if rec.state == "rejected" and not (rec.comment or "").strip():
                raise ValidationError(_("Si rechazas, debes indicar el motivo en Comentario."))