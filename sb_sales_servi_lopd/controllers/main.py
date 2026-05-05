from odoo import http
from odoo.http import request
from odoo import fields

class ServilopdController(http.Controller):

    @http.route('/lopd/form/<string:token>', type='http', auth='public', website=True)
    def lopd_form(self, token=None, **kwargs):

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request:
            return request.render('sb_sales_servi_lopd.token_invalid')

        # comprobar expiración
        if lopd_request.token_expiration and lopd_request.token_expiration < fields.Datetime.now():
            return request.render('sb_sales_servi_lopd.token_expired')

        return request.render('sb_sales_servi_lopd.lopd_form_template', {
            'request_record': lopd_request
        })