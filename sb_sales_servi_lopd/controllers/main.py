from odoo import http, fields
from odoo.http import request


class ServilopdController(http.Controller):

    @http.route('/lopd/form/<string:token>', type='http', auth='public', website=True)
    def lopd_form(self, token=None, **kwargs):

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request:
            return request.render('sb_sales_servi_lopd.token_invalid')

        if lopd_request.state == 'answered':
            return request.render('sb_sales_servi_lopd.lopd_already_submitted')

        if lopd_request.token_expiration and lopd_request.token_expiration < fields.Datetime.now():
            return request.render('sb_sales_servi_lopd.token_expired')

        return request.render('sb_sales_servi_lopd.lopd_form_template', {
            'request_record': lopd_request
        })

    @http.route('/lopd/form/submit', type='http', auth='public', website=True, csrf=False)
    def lopd_form_submit(self, **post):
        token = post.get('token')
        CURRENT_LOPD_VERSION = 'v1.0'

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if lopd_request.state == 'answered':
            return request.render('sb_sales_servi_lopd.lopd_already_submitted')

        if not lopd_request:
            return request.render('sb_sales_servi_lopd.token_invalid')
        
        if lopd_request.state == 'answered':
            return request.render('sb_sales_servi_lopd.lopd_already_submitted')
        
        if lopd_request.state == 'answered':
            return request.render('sb_sales_servi_lopd.lopd_already_submitted')
        
        ip = request.httprequest.remote_addr

        # Añadir campos/variables para el formulario.
        # Aquí busca los datos que tiene que aparecer para cambiarlos o dejarlos igual
        lopd_request.write({
            'company_name': post.get('company_name'),
            'fullname': post.get('fullname'),
            'email': post.get('email'),
            'vat': post.get('vat'),
            'phone': post.get('phone'),
            'mobile': post.get('mobile'),
            'lopd_accepted': True,
            'lopd_accepted_date': fields.Datetime.now(),
            'lopd_accept_ip': ip,
            'state': 'answered',
            'response_date': fields.Datetime.now(),
            'lopd_version': CURRENT_LOPD_VERSION,
        })

        lopd_request.partner_id.write({
            'lopd_state': 'signed',
            'company_name': post.get('company_name') or lopd_request.partner_id.company_name,
            'name': post.get('fullname') or lopd_request.partner_id.name,
            'vat': post.get('vat') or lopd_request.partner_id.vat,
            'phone': post.get('phone') or lopd_request.partner_id.phone,
            'mobile': post.get('mobile') or lopd_request.partner_id.mobile,
            'email': post.get('email') or lopd_request.partner_id.email,
        })

        lopd_request.partner_id.message_post(
            body="Cliente aceptó la LOPD desde formulario web."
        )

        return request.render('sb_sales_servi_lopd.lopd_thanks')