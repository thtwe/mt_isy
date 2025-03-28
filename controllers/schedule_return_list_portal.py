# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
from collections import OrderedDict

from odoo import http, _
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager
from odoo.exceptions import AccessError, MissingError
from odoo.http import request
from odoo.osv.expression import OR

class CustomerPortal(CustomerPortal):

    def _prepare_portal_layout_values(self):
        values = super(CustomerPortal, self)._prepare_portal_layout_values()
        domain = [('date_schedule_return','!=',False)]
        schedule_return_lists = request.env['internal.stock.transfer.details'].search_count(domain)
        values['schedule_return_lists_count'] = schedule_return_lists
        return values

    @http.route(['/my/schedule_return_list', '/my/schedule_return_list/page/<int:page>'], type='http', auth="user", website=True)
    def portal_schedule_return_list(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = []
        values = self._prepare_portal_layout_values()
        InternalStockTransfersDetails = request.env['internal.stock.transfer.details']

        #domain needo to modify for create user records only.

        searchbar_filters = {
           
        }

        searchbar_sortings = {
            'date_transfer': {'label': _('Transfer Date'), 'order': 'date_transfer desc'},
            'serial_number': {'label': _('Serial Number'), 'order': 'serial_number'},
            'product_id': {'label': _('Product'), 'order': 'product_id'},
        }

        searchbar_inputs = {
            'serial_number': {'input': 'serial_number', 'label': _('Search in Serial Number #')},
            'assigned_person': {'input': 'assigned_person', 'label': _('Search <span class="nolabel"> (in Assigned Person)</span>')},
            'source_location': {'input': 'source_location','label': _('Search <span class="nolabel">(in Source Location)</span>')},
            'destination_location': {'input': 'destination_location','label': _('Search <span class="nolabel">(in Destination Location)</span>')},
            'date_transfer': {'input': 'date_schedule','label': _('Search <span class="nolabel">(in Schedule Date)</span>')},
            'product_id': {'input': 'product_id','label': _('Search <span class="nolabel">(in Product)</span>')},
            'all': {'input': 'all', 'label': _('Search in All')},
        }
        domain +=[('date_schedule_return','!=',False)]
        # default sort by order
        if not sortby:
            sortby = 'serial_number'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        # if not filterby:
        #      filterby = 'all'
        # domain += searchbar_filters[filterby]['domain']

        # search
        if search and search_in:
            search_domain = []
            if search_in in ('assigned_person', 'all'):
                search_domain = OR([search_domain, [('assigned_person', 'ilike', search)]])
            if search_in in ('serial_number', 'all'):
                search_domain = OR([search_domain, [('serial_number', 'ilike', search)]])
            if search_in in ('date_transfer', 'all'):
                search_from = str(search) + ' 00:00:01'
                search_to = str(search) + ' 23:59:59'
                search_domain = OR([search_domain, [('date_transfer', '>=', search_from),('date_transfer','<=',search_to)]])
            if search_in in ('source_location', 'all'):
                search_domain = OR([search_domain, [('source_location', 'ilike', search)]])
            if search_in in ('destination_location', 'all'):
                search_domain = OR([search_domain, [('destination_location', 'ilike', search)]])
            if search_in in ('product_id', 'all'):
                search_domain = OR([search_domain, [('product_id', 'ilike', search)]])
            domain += search_domain

        # count for pager
        schedule_return_lists_count = InternalStockTransfersDetails.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/schedule_return_list",
            url_args={'sortby': sortby},
            total=schedule_return_lists_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        internal_stock_transfer_details = InternalStockTransfersDetails.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_stock_inventory_transfer_deetails_history'] = internal_stock_transfer_details.ids[:100]

        values.update({
            'schedule_return_lists': internal_stock_transfer_details,
            'page_name': 'schedule_return_list',
            'pager': pager,
            'default_url': '/my/schedule_return_list',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby
        })
        return request.render("mt_isy.portal_my_stock_inventory_transfer_details", values)
