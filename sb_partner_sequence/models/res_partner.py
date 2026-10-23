from odoo import api, fields, models


class InheritResPartner(models.Model):
    _inherit = 'res.partner'

    sequence_number = fields.Char(string='Number', copy=False, readonly=True, index=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Assign numbers to top-level contacts, respecting explicit numbers.

        A no_gap sequence is required to roll numbers back on failed creates.
        Existing production sequences must be switched explicitly after review.
        """
        prepared = []
        sequence_model = self.env['ir.sequence']
        for vals in vals_list:
            vals = dict(vals)
            if vals.get('parent_id'):
                vals['customer_rank'] = 0
            elif not vals.get('sequence_number'):
                customer_rank = vals.get('customer_rank', self.env.context.get('default_customer_rank', 0))
                supplier_rank = vals.get('supplier_rank', self.env.context.get('default_supplier_rank', 0))
                if customer_rank and customer_rank > 0:
                    vals['sequence_number'] = sequence_model.next_by_code('res.partner.customer.sequence')
                elif supplier_rank and supplier_rank > 0:
                    vals['sequence_number'] = sequence_model.next_by_code('res.partner.vendor.sequence')
            prepared.append(vals)
        return super().create(prepared)
