from odoo import models, fields
from odoo.exceptions import UserError
from datetime import datetime

class ResPartner(models.Model):
    _inherit = 'res.partner'

    lopd_state = fields.Selection([
        ('pending_send', 'Pdte. envío'),
        ('sent', 'Enviado'),
        ('signed', 'Firmado'),
        ('pending_review', 'Pdte. revisión'),
    ], string='Estado LOPD', default='pending_send')

    lopd_request_ids = fields.One2many(
        comodel_name='servilopd.request',
        inverse_name='partner_id',
        string='Solicitudes LOPD',
    )

    lopd_request_count = fields.Integer(
        string='Solicitudes LOPD',
        compute='_compute_lopd_request_count'
    )

    lopd_request_ids = fields.One2many(
        'servilopd.request',
        'partner_id',
        string='Solicitudes LOPD'
    )

    def _compute_lopd_request_count(self):
        for partner in self:
            partner.lopd_request_count = self.env[
                'servilopd.request'
            ].search_count([
                ('partner_id', '=', partner.id)
            ])

    def action_send_lopd_request(self):
        for partner in self:
            if not partner.email:
                partner.message_post(
                    body="No se pudo enviar formulario LOPD: cliente sin email."
                )
                partner.lopd_state = 'pending_review'
                continue

            existing_request = self.env['servilopd.request'].search([
                ('partner_id', '=', partner.id),
                ('state', '=', 'sent'),
                ('token_expiration', '>=', fields.Datetime.now()),
            ], limit=1)

            if existing_request:
                partner.message_post(
                    body="No se creó una nueva solicitud LOPD porque ya existe una solicitud enviada y vigente."
                )
                continue

            lopd_request = self.env['servilopd.request'].create({
                'name': f'LOPD - {partner.name}',
                'partner_id': partner.id,
                'email_to': partner.email,
                'state': 'sent',
                'sent_date': fields.Datetime.now(),
            })

            template = self.env.ref(
                'sb_sales_servi_lopd.mail_template_lopd_request',
                raise_if_not_found=False
            )

            if template:
                template.send_mail(lopd_request.id, force_send=True)

            partner.lopd_state = 'sent'

            partner.message_post(
                body="Formulario LOPD enviado al cliente."
            )
            
    def action_view_lopd_requests(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Solicitudes LOPD',
            'res_model': 'servilopd.request',
            'view_mode': 'tree,form',
            'domain': [('partner_id', '=', self.id)],
            'context': {
                'default_partner_id': self.id,
            }
        }