import base64
import json
from odoo import http, fields
from odoo.http import request, Response


class ServilopdController(http.Controller):
 
    @http.route('/', type='http', auth='public', website=True)
    def redirect_home_to_login(self, **kwargs):

        if request.session.uid:
            return request.redirect('/web')

        return request.redirect('/web/login')
    
    @http.route(
        '/lopd/states/<int:country_id>',
        type='json',
        auth='public',
        methods=['POST'],
        csrf=False
    )
    def lopd_get_states(self, country_id, **kwargs):

        states = request.env['res.country.state'].sudo().search([
            ('country_id', '=', country_id)
        ])

        return [
            {
                'id': state.id,
                'name': state.name,
            }
            for state in states
        ]

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

        countries = request.env['res.country'].sudo().search([])
        states = request.env['res.country.state'].sudo().search([
            ('country_id', '=', lopd_request.partner_id.country_id.id)
        ]) if lopd_request.partner_id.country_id else request.env['res.country.state'].sudo()

        return request.render('sb_sales_servi_lopd.lopd_form_template', {
            'request_record': lopd_request,
            'countries': countries,
            'states': states,
        })

    @http.route('/lopd/form/submit', type='http', auth='public', website=True, csrf=False)
    def lopd_form_submit(self, **post):

        token = post.get('token')
        
        required_fields = {
            'company_name': 'Nombre empresa',
            'fullname': 'Nombre completo',
            'email': 'Email',
            'vat': 'CIF/NIF/NIE',
        }

        for field, label in required_fields.items():
            if not post.get(field):
                return request.render('website.500', {
                    'error': f'El campo {label} es obligatorio.'
                })
        
        CURRENT_LOPD_VERSION = 'v1.0'

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request:
            return request.render('sb_sales_servi_lopd.token_invalid')

        if lopd_request.state == 'answered':
            return request.render('sb_sales_servi_lopd.lopd_already_submitted')

        if lopd_request.token_expiration and lopd_request.token_expiration < fields.Datetime.now():
            return request.render('sb_sales_servi_lopd.token_expired')

        headers = request.httprequest.headers

        ip = (
            headers.get('CF-Connecting-IP')
            or headers.get('X-Real-IP')
            or headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.httprequest.remote_addr
        )

        state_id = int(post.get('state_id')) if post.get('state_id') else False
        country_id = int(post.get('country_id')) if post.get('country_id') else False

        vat = post.get('vat')
        if vat:
            vat = vat.strip().upper()

        lopd_request.write({
            'company_name': post.get('company_name'),
            'fullname': post.get('fullname'),
            'email': post.get('email'),
            'vat': vat,
            'phone': post.get('phone'),
            'mobile': post.get('mobile'),
            'street': post.get('street'),
            'zip': post.get('zip'),
            'city': post.get('city'),
            'state_id': state_id or False,
            'country_id': country_id or False,
            'lopd_accepted': True,
            'lopd_accepted_date': fields.Datetime.now(),
            'lopd_accept_ip': ip,
            'state': 'answered',
            'response_date': fields.Datetime.now(),
            'lopd_version': lopd_request.document_id.version if lopd_request.document_id else CURRENT_LOPD_VERSION,
        })

        partner_vals = {
            'lopd_state': 'signed',
            'company_name': post.get('company_name') or lopd_request.partner_id.company_name,
            'name': post.get('fullname') or lopd_request.partner_id.name,
            'phone': post.get('phone') or lopd_request.partner_id.phone,
            'mobile': post.get('mobile') or lopd_request.partner_id.mobile,
            'email': post.get('email') or lopd_request.partner_id.email,
            'street': post.get('street') or lopd_request.partner_id.street,
            'zip': post.get('zip') or lopd_request.partner_id.zip,
            'city': post.get('city') or lopd_request.partner_id.city,
            'state_id': state_id or lopd_request.partner_id.state_id.id,
            'country_id': country_id or lopd_request.partner_id.country_id.id,
            'vat': vat or lopd_request.partner_id.vat,
        }

        lopd_request.partner_id.sudo().with_context(
            no_vat_validation=True
        ).write(partner_vals)

        lopd_request.partner_id.sudo().message_post(
            body="Cliente aceptó la LOPD desde formulario web.",
            subtype_xmlid="mail.mt_note",
        )

        return request.render('sb_sales_servi_lopd.lopd_thanks')
    
    @http.route('/lopd/document/<string:token>', type='http', auth='public', website=True)
    def lopd_document(self, token=None, **kwargs):
        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request or not lopd_request.document_id or not lopd_request.document_id.file:
            return request.not_found()

        document = lopd_request.document_id.sudo()
        pdf_content = base64.b64decode(document.file)

        filename = document.filename or 'lopd.pdf'

        return request.make_response(
            pdf_content,
            headers=[
                ('Content-Type', 'application/pdf'),
                ('Content-Disposition', f'inline; filename="{filename}"'),
            ]
        )
        
    @http.route('/lopd/form/preview', type='http', auth='public', website=True, csrf=False)
    def lopd_form_preview(self, **post):
        token = post.get('token')

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request:
            return "Token inválido"

        return request.render('sb_sales_servi_lopd.lopd_contract_preview', {
            'request_record': lopd_request,
            'post': post,
        })
        
    @http.route('/lopd/form/confirm', type='http', auth='public', website=True, csrf=False)
    def lopd_form_confirm(self, **post):

        token = post.get('token')

        lopd_request = request.env['servilopd.request'].sudo().search([
            ('token', '=', token)
        ], limit=1)

        if not lopd_request:
            return Response(
                json.dumps({
                    'success': False,
                    'error': 'Token inválido'
                }),
                content_type='application/json'
            )

        # Aquí irá luego:
        # - guardar partner
        # - guardar solicitud
        # - generar contrato
        # - enviar email

        return Response(
            json.dumps({
                'success': True
            }),
            content_type='application/json'
        )
            
    @http.route('/lopd/form/success', type='http', auth='public', website=True)
    def lopd_form_success(self, **kwargs):
        return request.render('sb_sales_servi_lopd.lopd_success_page')