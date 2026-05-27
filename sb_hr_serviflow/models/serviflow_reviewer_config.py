from odoo import models, fields


class ServiflowReviewerConfig(models.Model):
    _name = "serviflow.reviewer.config"
    _description = "Configuración de Revisores Serviflow"
    _order = "sequence, id"

    sequence = fields.Integer(
        string="Secuencia",
        default=10,
    )

    name = fields.Char(
        string="Tipo de revisor",
        required=True,
        help="Ejemplo: Revisor técnico, Revisor comercial, Revisor dirección.",
    )

    user_id = fields.Many2one(
        "res.users",
        string="Usuario revisor",
        required=True,
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )