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
        domain = [('assigned_to', '=', request.env.user.partner_id.id)]
        stock_report_lists = request.env['isy.stock.report'].search_count(
            domain)
        values['stock_reports_lists_count'] = stock_report_lists
        return values

    @http.route(['/my/isy_stock_report_teacher', '/my/isy_stock_report_teacher/page/<int:page>'], type='http', auth="user", website=True)
    def portal_isy_stock_report_teacher(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = [('assigned_to','=',request.env.user.partner_id.id)]
        values = self._prepare_portal_layout_values()
        IsyStockReport = request.env['isy.stock.report']

        #domain needo to modify for create user records only.

        # searchbar_filters = {
        #     'all': {'label': _('All Status'), 'domain': []},
        # }

        searchbar_sortings = {
            'location_id': {'label': _('Location'), 'order': 'location_id desc'},
            'serial_number': {'label': _('Serial Number'), 'order': 'serial_number'},
            'product_id': {'label': _('Product'), 'order': 'product_id'},
        }

        searchbar_inputs = {
            'serial_number': {'input': 'serial_number', 'label': _('Search in Serial Number #')},

        }
        domain += []
        # default sort by order
        if not sortby:
            sortby = 'serial_number'
        order = searchbar_sortings[sortby]['order']
        # default filter by value
        # if not filterby:
        #     filterby = 'all'
        # domain += searchbar_filters[filterby]['domain']

        # search
        if search and search_in:
            search_domain = []
            if search_in in ('serial_number', 'all'):
                search_domain = OR(
                    [search_domain, [('serial_number', 'ilike', search)]])
            domain += search_domain

        # count for pager
        stock_reports_lists_count = IsyStockReport.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/isy_stock_report_teacher",
            url_args={'sortby': sortby},
            total=stock_reports_lists_count,
            page=page,
            step=self._items_per_page
        )
        # content according to pager and archive selected
        isy_stock_report = IsyStockReport.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['my_isy_stock_report_history'] = isy_stock_report.ids[:100]

        values.update({
            'isy_stock_report_teacher_data': isy_stock_report,
            'page_name': 'isy_stock_report_teacher',
            'pager': pager,
            'default_url': '/my/isy_stock_report_teacher',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            #'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby
        })
        return request.render("mt_isy.portal_my_isy_stock_report_teacher", values)
