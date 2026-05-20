import secrets
import base64
import tempfile
import os
from datetime import timedelta
from odoo import models, fields, api
from docxtpl import DocxTemplate

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
    street = fields.Char(string="Calle")
    zip = fields.Char(string="C.P.")
    city = fields.Char(string="Ciudad")
    
    country_id = fields.Many2one(
        comodel_name='res.country',
        string='País',
    )

    state_id = fields.Many2one(
        comodel_name='res.country.state',
        string='Provincia',
    )

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
    
    document_id = fields.Many2one(
        'servilopd.document',
        string='Documento LOPD'
    )
    
    contract_docx = fields.Binary(
        string='Contrato DOCX generado',
        attachment=True,
        readonly=True,
    )

    contract_docx_filename = fields.Char(
        string='Nombre contrato DOCX',
        readonly=True,
    )

    contract_pdf = fields.Binary(
        string='Contrato PDF generado',
        attachment=True,
        readonly=True,
    )

    contract_pdf_filename = fields.Char(
        string='Nombre contrato PDF',
        readonly=True,
    )

    @api.model
    def create(self, vals):
        if not vals.get('token'):
            vals['token'] = secrets.token_urlsafe(32)

        if not vals.get('token_expiration'):
            vals['token_expiration'] = fields.Datetime.now() + timedelta(days=10)
            
        document = self.env['servilopd.document'].search([
            ('active', '=', True)
        ], limit=1)

        if document:
            vals['document_id'] = document.id

        record = super().create(vals)

        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        record.form_url = f"{base_url}/lopd/form/{record.token}"

        return record
    
    def action_resend_lopd_request(self):
        for record in self:
            record.token = secrets.token_urlsafe(32)
            record.token_expiration = fields.Datetime.now() + timedelta(days=10)

            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            record.form_url = f"{base_url}/lopd/form/{record.token}"

            document = self.env['servilopd.document'].search([
                ('active', '=', True)
            ], limit=1)

            vals = {
                'state': 'sent',
                'sent_date': fields.Datetime.now(),
            }

            if document:
                vals['document_id'] = document.id

            record.write(vals)

            template = self.env.ref(
                'sb_sales_servi_lopd.mail_template_lopd_request',
                raise_if_not_found=False
            )

            if template:
                template.send_mail(record.id, force_send=True)

            record.partner_id.write({
                'lopd_state': 'sent',
            })

            record.partner_id.message_post(
                body="Formulario LOPD reenviado."
            )

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

            record.partner_id.message_post(
                body="La solicitud LOPD expiró automáticamente."
            )
            
    def generate_contract_docx(self):
        self.ensure_one()

        if not self.document_id or not self.document_id.file:
            return False

        template_content = base64.b64decode(self.document_id.file)

        with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as template_file:
            template_file.write(template_content)
            template_path = template_file.name

        output_path = template_path.replace('.docx', '_generated.docx')

        doc = DocxTemplate(template_path)

        context = {
            'fecha_contrato': fields.Date.today().strftime('%d/%m/%Y'),
            'cliente_nombre': self.company_name or self.partner_id.company_name or self.partner_id.name or '',
            'cliente_representante': self.fullname or self.partner_id.name or '',
            'cliente_vat': self.vat or self.partner_id.vat or '',
            'cliente_email': self.email or self.partner_id.email or '',
            'cliente_direccion': self.street or self.partner_id.street or '',
            'cliente_cp': self.zip or self.partner_id.zip or '',
            'cliente_ciudad': self.city or self.partner_id.city or '',
            'cliente_provincia': self.state_id.name or self.partner_id.state_id.name or '',
            'cliente_pais': self.country_id.name or self.partner_id.country_id.name or '',
        }

        doc.render(context)
        doc.save(output_path)

        with open(output_path, 'rb') as generated_file:
            generated_content = generated_file.read()

        filename = f"Contrato_LOPD_{self.partner_id.name or 'cliente'}.docx"

        self.write({
            'contract_docx': base64.b64encode(generated_content),
            'contract_docx_filename': filename,
        })

        os.unlink(template_path)
        os.unlink(output_path)

        return True