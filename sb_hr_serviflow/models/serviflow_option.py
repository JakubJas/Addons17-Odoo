from odoo import fields, models, api


class SbHrServiflowOption(models.Model):
    _name = 'sb.hr.serviflow.option'
    _description = 'Opción global de Serviflow'
    _order = 'sequence, id'

    name = fields.Char(
        string='Nombre',
        required=True,
    )
    code = fields.Char(
        string='Código',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Ya existe una opción con ese nombre.'),
    ]

    @api.model
    def get_active(self):
        param = self.env['ir.config_parameter'].sudo().get_param(
            'sb_hr_serviflow.active_option_id'
        )
        return self.browse(int(param)) if param else self.browse()
