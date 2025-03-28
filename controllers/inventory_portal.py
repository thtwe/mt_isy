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
        domain = []
        stock_inventories_count = request.env['internal.stock.transfer'].search_count(domain)
        values['stock_inventories_count'] = stock_inventories_count
        return values

    @http.route(['/my/stock_inventories', '/my/stock_inventories/page/<int:page>'], type='http', auth="user", website=True)
    def portal_stock_inventories(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = []
        values = self._prepare_portal_layout_values()
        InternalStockTransfers = request.env['internal.stock.transfer']

        #domain needo to modify for create user records only.

        searchbar_filters = {
            'all': {'label': _('All Status'), 'domain': []},
            'state_draft': {'label': _('Draft'), 'domain': [('state', '=', 'draft')]},
            'state_first_approval': {'label': _('First Approval'), 'domain': [('state', '=', 'firstapproval')]},
            'state_second_approval': {'label': _('Second Approval'), 'domain': [('state', '=', 'secondapproval')]},
            'state_reserved': {'label': _('Reserved'), 'domain': [('state', '=', 'reserved')]},
            'state_done': {'label': _('Done'), 'domain': [('state', '=', 'done')]},
            'state_cancelled': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancelled')]},
        }

        searchbar_sortings = {
            'date_schedule': {'label': _('Schedule Date'), 'order': 'date_schedule desc'},
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search in Ref #')},
            'assigned_person': {'input': 'assigned_person', 'label': _('Search <span class="nolabel"> (in Assigned Person)</span>')},
            'source_location': {'input': 'source_location','label': _('Search <span class="nolabel">(in Source Location)</span>')},
            'destination_location': {'input': 'destination_location','label': _('Search <span class="nolabel">(in Destination Location)</span>')},
            'date_schedule': {'input': 'date_schedule','label': _('Search <span class="nolabel">(in Schedule Date)</span>')},
            'all': {'input': 'all', 'label': _('Search in All')},
        }
        domain +=[]# [('key_type', '=', 'maintenance'), '|', ('create_uid', '=', request.env.user.id),  ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
        # default sort by order
        if not sortby:
            sortby = 'name'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        if not filterby:
             filterby = 'all'
        domain += searchbar_filters[filterby]['domain']

        # search
        if search and search_in:
            search_domain = []
            if search_in in ('assigned_person', 'all'):
                search_domain = OR([search_domain, [('assigned_person', 'ilike', search)]])
            if search_in in ('name', 'all'):
                search_domain = OR([search_domain, [('name', 'ilike', search)]])
            if search_in in ('date_schedule', 'all'):
                search_from = str(search) + ' 00:00:01'
                search_to = str(search) + ' 23:59:59'
                search_domain = OR([search_domain, [('date_schedule', '>=', search_from),('date_schedule','<=',search_to)]])
            if search_in in ('source_location', 'all'):
                search_domain = OR([search_domain, [('source_location', 'ilike', search)]])
            if search_in in ('destination_location', 'all'):
                search_domain = OR([search_domain, [('destination_location', 'ilike', search)]])
            domain += search_domain

        # count for pager
        stock_inventories_count = InternalStockTransfers.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/stock_inventories",
            url_args={'sortby': sortby},
            total=stock_inventories_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        internal_stock_transfers = InternalStockTransfers.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_stock_inventory_history'] = internal_stock_transfers.ids[:100]

        values.update({
            'stock_inventories': internal_stock_transfers,
            'page_name': 'stock_inventory',
            'pager': pager,
            'default_url': '/my/stock_inventories',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby
        })
        return request.render("mt_isy.portal_my_stock_inventory", values)
