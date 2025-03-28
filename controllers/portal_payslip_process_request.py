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
        domain = [('request_employee_id.user_id', '=', request.env.user.id)]
        payslip_process_requests_count = request.env['hr.payslip.process.request'].search_count(
            domain)
        values['payslip_process_requests_count'] = payslip_process_requests_count

        # Get the latest total_car value for the current user
        total_car_amt = self._get_latest_total_car()
        values['total_car_amt'] = total_car_amt

        return values

    def _get_latest_total_car(self):
        accumulated_savings = request.env['account.move.line'].sudo().search([
            ('account_id.savings_for_education', '=', True),
            ('partner_id', '=', request.env.user.address_id.id),
            ('move_id.state', '=', 'posted')
        ])
        total_car_amt = sum(accumulated_savings.mapped('credit')) - sum(accumulated_savings.mapped('debit'))
        return total_car_amt

    @http.route(['/my/payslip_process_requests', '/my/payslip_process_requests/page/<int:page>'], type='http', auth="user", website=True)
    def portal_payslip_process_requests(self, page=1, sortby=None, filterby=None, search=None, search_in='all', **kw):
        domain = []
        values = self._prepare_portal_layout_values()
        PayslipProcessRequests = request.env['hr.payslip.process.request']

        #domain needo to modify for create user records only.

        searchbar_filters = {
            'all': {'label': _('All Status'), 'domain': []},
            'state_draft': {'label': _('Draft'), 'domain': [('state', '=', 'draft')]},
            'state_waiting_for_approval': {'label': _('Waiting For Approval'), 'domain': [('state', '=', 'waitingforapproval')]},
            'state_done': {'label': _('Done'), 'domain': [('state', '=', 'done')]},
            'state_cancelled': {'label': _('Cancelled'), 'domain': [('state', '=', 'cancelled')]},
        }

        searchbar_sortings = {  
            'name': {'label': _('Reference'), 'order': 'name desc'},
            'state': {'label': _('Status'), 'order': 'state'},
        }

        searchbar_inputs = {
            'name': {'input': 'name', 'label': _('Search in Ref #')},
            'all': {'input': 'all', 'label': _('Search in All')},
        }
        # [('key_type', '=', 'maintenance'), '|', ('create_uid', '=', request.env.user.id),  ('message_partner_ids', 'in', [request.env.user.partner_id.id])]
        domain += [('request_employee_id.user_id', '=', request.env.user.id)]
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
            if search_in in ('name', 'all'):
                search_domain = OR(
                    [search_domain, [('name', 'ilike', search)]])
            domain += search_domain

        # count for pager
        payslip_process_requests_count = PayslipProcessRequests.sudo().search_count(domain)
        # pager

        pager = portal_pager(
            url="/my/payslip_process_requests",
            url_args={'sortby': sortby},
            total=payslip_process_requests_count,
            page=page,
            step=self._items_per_page
        )

        payslip_process_requests = PayslipProcessRequests.sudo().search(
            domain, order=order, limit=self._items_per_page, offset=pager['offset'])
        request.session['payslip_process_requests_history'] = payslip_process_requests.ids[:100]

        values.update({
            'payslip_process_requests': payslip_process_requests,
            'page_name': 'payslip_process_request',
            'pager': pager,
            'default_url': '/my/payslip_process_requests',
            'searchbar_inputs': searchbar_inputs,
            'search_in': search_in,
            'searchbar_sortings': searchbar_sortings,
            'sortby': sortby,
            'searchbar_filters': OrderedDict(sorted(searchbar_filters.items())),
            'filterby': filterby,
        })
        return request.render("mt_isy.portal_my_payslip_process_requests", values)
