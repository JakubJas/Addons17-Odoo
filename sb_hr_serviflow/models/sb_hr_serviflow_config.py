from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    serviflow_active_option_id = fields.Many2one(
        'sb.hr.serviflow.option',
        string='Flujo activo',
        config_parameter='sb_hr_serviflow.active_option_id',
        help='Selecciona el flujo activo global para todas las empresas.',
    )
