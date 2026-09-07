from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

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
        domain=lambda self: [
            (
                "groups_id",
                "in",
                [
                    self.env.ref(
                        "sb_hr_serviflow.group_serviflow_manager"
                    ).id
                ],
            )
        ],
    )

    active = fields.Boolean(
        string="Activo",
        default=True,
    )
    
    
    @api.constrains("user_id")
    def _check_user_is_serviflow_manager(self):
        group = self.env.ref(
            "sb_hr_serviflow.group_serviflow_manager",
            raise_if_not_found=False
        )

        for record in self:
            if (
                record.user_id
                and group
                and group not in record.user_id.groups_id
            ):
                raise ValidationError(
                    _(
                        "El usuario seleccionado debe pertenecer "
                        "al grupo Serviflow / Responsable."
                    )
                )