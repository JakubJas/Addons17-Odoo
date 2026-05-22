from odoo import models, fields, api


class ServilopdDocument(models.Model):
    _name = 'servilopd.document'
    _description = 'Documento LOPD'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Nombre',
        required=True,
        tracking=True,
    )

    version = fields.Char(
        string='Versión',
        required=True,
        tracking=True,
    )

    file = fields.Binary(
        string='Plantilla DOCX',
        required=True,
        attachment=True,
    )

    filename = fields.Char(
        string='Nombre archivo plantilla',
    )

    active = fields.Boolean(
        string='Activo',
        default=True,
        tracking=True,
    )

    display_name = fields.Char(
        string='Nombre completo',
        compute='_compute_display_name',
        store=True,
    )
    
    body_html = fields.Html(
        string='Texto del contrato',
        sanitize=False,
        translate=True,
    )

    @api.depends('name', 'version')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name or ''} - {record.version or ''}"