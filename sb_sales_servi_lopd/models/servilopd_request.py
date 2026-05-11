import secrets
from datetime import timedelta
from odoo import models, fields, api

class ServilopdRequest(models.Model):
    _name = 'servilopd.request'
    _description = 'Solicitud de formulario LOPD'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Referencia',
        required=True,
        default='Nueva solicitud',
        tracking=True,
    )

    partner_id = fields.Many2one(
        comodel_name='res.partner',
        string='Cliente/Proveedor',
        required=True,
        ondelete='cascade',
        tracking=True,
    )

    email_to = fields.Char(
        string='Email destinatario',
        required=True,
        tracking=True,
    )

    state = fields.Selection([
        ('draft', 'Borrador'),
        ('sent', 'Enviado'),
        ('answered', 'Respondido'),
        ('expired', 'Expirado'),
        ('cancelled', 'Cancelado'),
    ], string='Estado', default='draft', tracking=True)

    sent_date = fields.Datetime(
        string='Fecha de envío',
        readonly=True,
    )

    response_date = fields.Datetime(
        string='Fecha de respuesta',
        readonly=True,
    )

    token = fields.Char(
        string='Token',
        readonly=True,
        copy=False,
        index=True,
    )

    token_expiration = fields.Datetime(
        string='Fecha expiración token',
        readonly=True,
        copy=False,
    )

    lopd_accept_ip = fields.Char(
        string='IP aceptación LOPD',
        readonly=True,
    )

    fullname = fields.Char(string='Nombre')
    email = fields.Char(string='Email recibido')
    lastname = fields.Char(string='Apellidos')
    vat = fields.Char(string='CIF/NIF')
    company_name = fields.Char(string='Empresa')
    phone = fields.Char(string='Teléfono')
    mobile = fields.Char(string='Móvil')

    lopd_accepted = fields.Boolean(
        string='LOPD aceptada',
        readonly=True,
    )

    lopd_accepted_date = fields.Datetime(
        string='Fecha aceptación LOPD',
        readonly=True,
    )

    form_url = fields.Char(
        string='URL formulario',
        readonly=True,
        copy=False,
    )

    lopd_version = fields.Char(
        string='Versión LOPD',
        readonly=True,
    )

    @api.model
    def create(self, vals):
        if not vals.get('token'):
            vals['token'] = secrets.token_urlsafe(32)

        if not vals.get('token_expiration'):
            vals['token_expiration'] = fields.Datetime.now() + timedelta(days=10)

        record = super().create(vals)

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        record.form_url = f"{base_url}/lopd/form/{record.token}"

        return record
    
    def action_resend_lopd_request(self):
        for record in self:
            record.token = secrets.token_urlsafe(32)
            record.token_expiration = fields.Datetime.now() + timedelta(minutes=1)

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            record.form_url = f"{base_url}/lopd/form/{record.token}"

            record.write({
                'state': 'sent',
                'sent_date': fields.Datetime.now(),
            })

            template = self.env.ref(
                'sb_sales_servi_lopd.mail_template_lopd_request',
                raise_if_not_found=False
            )

            if template:
                template.send_mail(record.id, force_send=True)

            record.partner_id.write({
                'lopd_state': 'sent',
            })

    def cron_expire_lopd_requests(self):
        expired_requests = self.search([
            ('state', '=', 'sent'),
            ('token_expiration', '<', fields.Datetime.now()),
        ])

        for record in expired_requests:
            record.write({
                'state': 'expired',
            })

            record.partner_id.write({
                'lopd_state': 'pending_review',
            })