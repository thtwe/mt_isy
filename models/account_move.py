# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, float_is_zero
from datetime import date, datetime, time

from odoo.osv import expression


import logging
_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # migrate from AccountInovoice
    x_studio_approver = fields.Many2one('res.users',string='Approver',related='invoice_line_ids.purchase_order_id.x_studio_approver')
    x_studio_company = fields.Char(string='Company (OLD)')
    x_studio_created_by = fields.Many2one('res.users',string='Created by',related='invoice_line_ids.purchase_order_id.create_uid')
    x_studio_Date_for_invoice = fields.Date(string='Date for Invoice')
    x_studio_father_name = fields.Char(string='Father Name',related='partner_id.guardian_1_name')
    x_studio_field_hrbLx = fields.Many2one('account.payment.method',string='Payment Method')
    x_studio_field_k5kIh = fields.Char(string='New Related Field',related='partner_id.x_studio_guardian2_name')
    x_studio_grade = fields.Char(string='Grade',related='partner_id.grade_level')
    x_studio_guardian_1_email = fields.Char(string='Guardian 1 Email',related='partner_id.guardian_1_email')
    x_studio_guardian_2_email = fields.Char(string='Guardian 2 Email',related='partner_id.guardian_2_email')

    x_studio_invoice_reference = fields.Char(string='Invoice Reference')

    x_studio_is_asset = fields.Boolean(string='Asset')
    x_studio_is_asset_1 = fields.Boolean(string='Is Asset',related='invoice_line_ids.purchase_order_id.is_asset')
    x_studio_mother_name = fields.Char(string='Mother Name',related='partner_id.guardian_2_name')
    x_studio_note = fields.Char(string='Note',related='invoice_line_ids.purchase_order_id.x_studio_notes_1')
    x_studio_others = fields.Boolean(string='Others',default=True)
    x_studio_td_bank = fields.Boolean(string='TD Bank')
    x_studio_to_pay = fields.Many2one('hr.employee',string='Purchaser',related='invoice_line_ids.purchase_order_id.x_studio_field_YvZf6')
    x_studio_vendor_pick_up = fields.Boolean(string='Vendor Pickup Payment',related='invoice_line_ids.purchase_order_id.x_studio_pick_up_at_cashier')
    origin = fields.Char('Source Document',related='invoice_line_ids.purchase_order_id.name')
    purchase_id = fields.Many2one('purchase.order', store=True, readonly=True,
        states={'draft': [('readonly', False)]},
        string='Purchase Order',
        help="Auto-complete from a past purchase order.")

    @api.onchange('purchase_vendor_bill_id', 'purchase_id')
    def _onchange_purchase_auto_complete(self):
        ''' Load from either an old purchase order, either an old vendor bill.

        When setting a 'purchase.bill.union' in 'purchase_vendor_bill_id':
        * If it's a vendor bill, 'invoice_vendor_bill_id' is set and the loading is done by '_onchange_invoice_vendor_bill'.
        * If it's a purchase order, 'purchase_id' is set and this method will load lines.

        /!\ All this not-stored fields must be empty at the end of this function.
        '''
        if self.purchase_vendor_bill_id.vendor_bill_id:
            self.invoice_vendor_bill_id = self.purchase_vendor_bill_id.vendor_bill_id
            self._onchange_invoice_vendor_bill()
        elif self.purchase_vendor_bill_id.purchase_order_id:
            self.purchase_id = self.purchase_vendor_bill_id.purchase_order_id
        self.purchase_vendor_bill_id = False

        if not self.purchase_id:
            return

        # Copy data from PO
        invoice_vals = self.purchase_id.with_company(self.purchase_id.company_id)._prepare_invoice()
        invoice_vals['currency_id'] = self.line_ids and self.currency_id or invoice_vals.get('currency_id')
        del invoice_vals['ref']
        self.update(invoice_vals)

        # Copy purchase lines.
        po_lines = self.purchase_id.order_line - self.line_ids.mapped('purchase_line_id')
        new_lines = self.env['account.move.line']
        sequence = max(self.line_ids.mapped('sequence')) + 1 if self.line_ids else 10
        for line in po_lines.filtered(lambda l: not l.display_type):
            line_vals = line._prepare_account_move_line(self)
            line_vals.update({'sequence': sequence})
            new_line = new_lines.new(line_vals)
            sequence += 1
            new_line.account_id = new_line._get_computed_account()
            new_line._onchange_price_subtotal()
            new_lines += new_line
        new_lines._onchange_mark_recompute_taxes()

        # Compute invoice_origin.
        origins = set(self.line_ids.mapped('purchase_line_id.order_id.name'))
        self.invoice_origin = ','.join(list(origins))

        # Compute ref.
        refs = self._get_invoice_reference()
        self.ref = ', '.join(refs)

        # Compute payment_reference.
        if len(refs) == 1:
            self.payment_reference = refs[0]

        # self.purchase_id = False
        self._onchange_currency()

    def _set_next_sequence(self):
        """Set the next sequence.

        This method ensures that the field is set both in the ORM and in the database.
        This is necessary because we use a database query to get the previous sequence,
        and we need that query to always be executed on the latest data.

        :param field_name: the field that contains the sequence.
        """
        self.ensure_one()
        last_sequence = self._get_last_sequence()
        new = not last_sequence
        if new:
            last_sequence = self._get_last_sequence(relaxed=True) or self._get_starting_sequence()
        format, format_values = self._get_sequence_format_param(last_sequence)
        if new:
            # format_values['seq'] = 0 # ISY will not reset sequence number per month
            format_values['seq'] = format_values['seq'] or 0
            format_values['year'] = self[self._sequence_date_field].year % (10 ** format_values['year_length'])
            format_values['month'] = self[self._sequence_date_field].month
        format_values['seq'] = format_values['seq'] + 1

        self[self._sequence_field] = format.format(**format_values)
        self._compute_split_sequence()

    # def preview_invoice(self):
    #     self.ensure_one()
    #     return {
    #         'type': 'ir.actions.act_url',
    #         'target': 'new',
    #         'url': self.get_portal_url(),
    #     }

    def _compute_access_url(self):
        super(AccountMove, self)._compute_access_url()
        for move in self:
            if move.is_invoice():
                move.access_url = '/my/invoices/%s' % (move.id)
            else:
                move.access_url = '/my/journalentry/%s' % (move.id)

    #def write(self, values):
    #    for move in self:
    #        for move_line in move.line_ids:
    #            warning_msg = []
    #            budget_account_dict = {}
    #            account_analytic = []
    #            if 'state' in values and values.get('state') in ('posted','draft') and move.state!='posted':  
    #                move_line.accouting_budget_warning(move_line.move_id, move_line, warning_msg, budget_account_dict, account_analytic, update=True)
    #    res = super(AccountMove, self).write(values)
    #    return res


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    # migrate from AccountInovoiceLine
    x_studio_approver = fields.Many2one('res.users',string='Approver',related='move_id.x_studio_approver')
    x_studio_bill_date = fields.Date(string='Bill Date',related='move_id.invoice_date')
    x_studio_bill_no = fields.Char(string='Bill No.',related='move_id.name')
    x_studio_charge_date = fields.Date(string='Charge Date',related='move_id.invoice_date')
    x_studio_created_by = fields.Many2one('res.users',string='Created By',related='move_id.x_studio_created_by')
    x_studio_due_date = fields.Date(string='Due Date',related='move_id.invoice_date_due')
    x_studio_field_25yO5 = fields.Date(string='New Related Field',related='move_id.x_studio_date_for_invoice')
    x_studio_field_pIomB = fields.Char(string='New Related Field',related='move_id.name')
    x_studio_note = fields.Char(string='Note',related='move_id.x_studio_note')
    x_studio_purchaser = fields.Many2one('hr.employee',string='Purchaser',related='move_id.x_studio_to_pay')
    x_studio_source_document = fields.Char(string='Source Document',related='move_id.origin')
    # x_studio_student = fields.Many2one(string='Student')
    x_studio_student_1 = fields.Many2one('res.partner',string='Student',related='move_id.partner_id')
    x_studio_vendor = fields.Many2one('res.partner',string='Vendor',related='move_id.partner_id')
    origin = fields.Char('Source Document',related='move_id.purchase_id.name')

    asset_model_id = fields.Many2one('account.asset',string='Asset Category',domain=[('state','=','model')])


    def budget_account_dict(self, account_id, price_subtotal, budget_account_dict, account_analytic,product_id=False,date_from=False,date_to=False):
        # if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
        #     currency_id = self.currency_id
        #     rate = currency_id.with_context(date=self.date_order)
        #     price_subtotal = currency_id._convert(price_subtotal, self.company_id.currency_id, self.company_id, self.date_order or fields.Date.today())
        
        #check pending PO amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('order_id.state','!=','cancel'),('order_id.invoice_count','=',0),('company_id','=',self.company_id.id)]
        if self.capex_group_id:
            domain += [('order_id.capex_group_id','=',self.capex_group_id.id)]
        po_lines = self.env['purchase.order.line'].sudo().search(domain)
        for line in po_lines.filtered(lambda x:x.order_id.name not in (self.origin or '')):
            subtotal = line.price_subtotal
            if line.order_id.currency_id and line.order_id.company_id and line.order_id.currency_id != line.order_id.company_id.currency_id:
                currency_id = line.order_id.currency_id
                rate = currency_id.with_context(date=line.order_id.date_order)
                subtotal = currency_id._convert(subtotal, line.order_id.company_id.currency_id, line.order_id.company_id, line.order_id.date_order or fields.Date.today())
            _logger.debug('####################################################### Other PO amount')
            _logger.debug('%s, %s, %s'%(line.order_id.id,line.order_id.name,subtotal))
            price_subtotal += subtotal

        #check pending Advance amount
        # domain = [('x_studio_anticipated_account_code','=',product_id),('id','!=',self.id),('state','in',('draft','confirm','approved_hr_manager','paid')),('company_id','=',self.company_id.id)]
        domain = [('x_studio_anticipated_account_code.property_account_expense_id','=',account_id.id),('state','not in',('cancel','rejected','cleared')),('company_id','=',self.company_id.id)]
        # ref = (self.ref or '').split('[')[0]
        # if ref: # 'not ilike' operator is not working
        #     domain += [('name','!=',ref)]
        if self.capex_group_id:
            domain += [('capex_group_id','=',self.capex_group_id.id)]
        lines = self.env['employee.advance.expense'].sudo().search(domain)
        for line in lines.filtered(lambda x:x.name not in (self.ref or '')):
            subtotal = line.total_amount_expense
            if line.currency_id and line.company_id and line.currency_id != line.company_id.currency_id:
                currency_id = line.currency_id
                rate = currency_id.with_context(date=line.request_date)
                subtotal = currency_id._convert(subtotal, line.company_id.currency_id, line.company_id, line.request_date or fields.Date.today())
            _logger.debug('####################################################### Other Advance amount')
            _logger.debug('%s, %s, %s'%(line.id,line.name,subtotal))
            price_subtotal += subtotal

        #check other Reimbursement amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('advance_line_id.state','in',('draft','confirm','approved_hr_manager','paid')),('advance_line_id.company_id','=',self.company_id.id)]
        if self.capex_group_id:
            domain += [('advance_line_id.capex_group_id','=',self.capex_group_id.id)]
        lines = self.env['advance.expense.line'].sudo().search(domain)
        for line in lines.filtered(lambda x:x.name not in (self.ref or '')):
            subtotal = line.total_amount
            if line.advance_line_id.currency_id and line.advance_line_id.company_id and line.advance_line_id.currency_id != line.advance_line_id.company_id.currency_id:
                currency_id = line.advance_line_id.currency_id
                rate = currency_id.with_context(date=line.advance_line_id.request_date)
                subtotal = currency_id._convert(subtotal, line.advance_line_id.company_id.currency_id, line.advance_line_id.company_id, line.advance_line_id.request_date or fields.Date.today())
            _logger.debug('####################################################### Other Reimbursement amount')
            _logger.debug('%s, %s, %s'%(line.advance_line_id.id,line.advance_line_id.name,subtotal))
            price_subtotal += subtotal

        #check pending Invoice
        domain = [('account_id.code','=',account_id.code),('id','!=',self.id),('move_id.state','=','draft'),('date','>=',date_from),('date','<=',date_to)]
        if self.capex_group_id:
            domain += [('capex_group_id','=',self.capex_group_id.id)]
        aml_lines = self.env['account.move.line'].sudo().search(domain)

        for line in aml_lines:
            subtotal = line.debit-line.credit
            _logger.debug('####################################################### Other Invoice amount')
            _logger.debug('%s, %s, %s'%(line.move_id.id,line.move_id.name,subtotal))
            price_subtotal += subtotal

        # if account_id.id in account_analytic:
        #     budget_account_dict[account_id.id].append(price_subtotal)
        # else:
        #     account_analytic.append(account_id.id)
        #     budget_account_dict[account_id.id] = [price_subtotal]
        if account_id.id not in account_analytic:
            account_analytic.append(account_id.id)
        budget_account_dict[account_id.id] = [price_subtotal]
        return {'budget_account_dict': budget_account_dict,
                'account_analytic': account_analytic,
                'account_id': account_id}

    def accouting_budget_warning(self, move_id, lines, warning_msg, budget_account_dict, account_analytic, update=False):
        for line in lines:
            # if not update:
            date_planned = line.date
            account_id = line.account_id
            asset = False
            if account_id and not account_id.no_budget:
                total_price = line.debit-line.credit
                domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                ('state', '=', 2), ('account_id.code', '=', account_id.code)] # including ISYA
                budget_id = self.env['budgetextension.budget'].sudo().search(domain)
                if budget_id:
                    practical_amount = sum(budget_id.mapped('practical_amount')) or 0
                    planned_amount = sum(budget_id.mapped('planned_amount')) or 0
                    vals = line.budget_account_dict(account_id, total_price, budget_account_dict, account_analytic,product_id=False,date_from=budget_id[0].start_date,date_to=budget_id[0].end_date)
                    total_price = (sum(budget_account_dict.get(account_id.id)))
                    
                    if ( practical_amount + total_price) > planned_amount:
                        warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % account_id.display_name)
                else: # asset/capex budget
                    if account_id.workinprocess and not line.capex_group_id:
                        raise UserError('You will need to put Capex Group for this account.')
                    elif line.capex_group_id:
                        group_name = line.capex_group_id.name
                    else:
                        group_name = self.env['x.capex.group'].search([('account_ids','in',account_id.id)],limit=1).name
                    domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                    budget_id = self.env['x_capex'].search(domain)
                    if budget_id:
                        budget_amount = budget_id.x_budget_total_total*-1
                        actual_amount = budget_id.x_total_total*-1
                        vals = line.budget_account_dict(account_id, total_price, budget_account_dict, account_analytic,product_id=False,date_from=budget_id[0].x_start_date,date_to=budget_id[0].x_end_date)
                        total_price = (sum(budget_account_dict.get(account_id.id)))
                        
                        if not account_id.workinprocess:
                            domain = [('account_id.workinprocess','=',True),('move_id','=',move_id.id)]
                            if self.capex_group_id:
                                domain += [('capex_group_id','=',self.capex_group_id.id)]
                            aml_lines = self.env['account.move.line'].sudo().search(domain)

                            for line in aml_lines:
                                subtotal = line.debit-line.credit
                                _logger.debug('####################################################### Other workinprocess amount')
                                _logger.debug('%s, %s, %s'%(line.move_id.id,line.move_id.name,subtotal))
                                total_price += subtotal

                        _logger.debug('########################### actual %s, total %s, budget %s'%(actual_amount,total_price,budget_amount))
                        if (actual_amount + total_price) > budget_amount:
                            warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % account_id.name)                    
                    elif account_id.code.startswith("5") or account_id.name.startswith("5"):
                        raise UserError("%s doesn't have the current fiscal year budget"%(account_id.display_name))
            # else:
            #     raise UserError("%s is not an expense type. \n Please contact Odoo team to choose the correct account code."%(account_id.display_name))
        if warning_msg:
            raise UserError(_(''.join(warning_msg)))

    #@api.model_create_multi
    #def create(self, values):
    #    move_line = super(AccountMoveLine, self).create(values)
    #    warning_msg = []
    #    budget_account_dict = {}
    #    account_analytic = []   
    #    self.accouting_budget_warning(move_line.move_id, move_line, warning_msg, budget_account_dict, account_analytic, update=False)
    #    return move_line

    #def write(self, values):
    #    res = super(AccountMoveLine, self).write(values)
    #    for move_line in self:
    #        warning_msg = []
    #        budget_account_dict = {}
    #        account_analytic = []
    #        if 'debit' in values or 'credit' in values or 'capex_group_id' in values or 'account_id' in values:  
    #            move_line.accouting_budget_warning(move_line.move_id, move_line, warning_msg, budget_account_dict, account_analytic, update=True)
    #    return res


class CurrencyRate(models.Model):
    _inherit = "res.currency.rate"

    currency_id = fields.Many2one('res.currency', string='Currency', readonly=False, required=True, ondelete="cascade")