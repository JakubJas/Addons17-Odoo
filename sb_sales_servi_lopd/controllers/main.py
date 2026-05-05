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

        if not lopd_request:
            return request.render('sb_sales_servi_lopd.token_invalid')

        lopd_request.write({
            'state': 'answered',
            'response_date': fields.Datetime.now(),
        })

        lopd_request.partner_id.write({
            'lopd_state': 'signed',
        })

        return request.render('sb_sales_servi_lopd.lopd_thanks')