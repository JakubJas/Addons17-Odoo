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

    # lopd_last_request_id = fields.Many2one(
    #     comodel_name='servilopd.request',
    #     string='Última solicitud LOPD',
    #     readonly=True,
    # )

    # lopd_last_request_date = fields.Datetime(
    #     string='Fecha última solicitud',
    #     readonly=True,
    # )

    def action_send_lopd_request(self):
        for partner in self:
            if not partner.email:
                raise UserError("El cliente no tiene email definido")

            request = self.env['servilopd.request'].create({
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
                template.send_mail(request.id, force_send=True)

            # actualizar estado del partner
            partner.lopd_state = 'sent'