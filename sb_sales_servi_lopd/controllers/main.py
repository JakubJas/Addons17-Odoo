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

        # Añadir campos para el formulario
        lopd_request.write({
            'firstname': post.get('firstname'),
            'email': post.get('email'),
            'lopd_accepted': True,
            'lopd_accepted_date': fields.Datetime.now(),
            'lopd_accept_ip': ip,
            'state': 'answered',
            'response_date': fields.Datetime.now(),
        })

        lopd_request.partner_id.write({
            'lopd_state': 'signed',
        })

        return request.render('sb_sales_servi_lopd.lopd_thanks')