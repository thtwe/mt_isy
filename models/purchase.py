# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
import datetime
from odoo.tools.float_utils import float_compare, float_is_zero, float_round
from itertools import groupby
import logging
_logger = logging.getLogger(__name__)


# class PurchaseOrder(models.Model):
#     _inherit = "purchase.order"

#     @api.depends('order_line.invoice_lines.invoice_id')
#     def _get_invoiced_status(self):
#         invoice_count = len(self.invoice_ids)
#         paid_invoice_status = len(self.invocie_ids.filtered(lambda x: x.state=='paid'))
#         partial_invoice_status = len(self.invocie_ids.filtered(lambda x: x.state in ('open','in_payment')))
#         if partial_invoice_status:
#             self.payment_status = 'partial'
#         if invoice_count == paid_invoice_status:
#             self.payment_status = 'paid'


#     payment_status = fields.Selection([('partial','Partial Paid'),('paid','Paid')], compute='_get_invoiced_status', store=True, readonly=True, copy=False, string = "Payment Status")
class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    company_currency_id = fields.Many2one('res.currency','Company Currency',default=lambda self: self.env.user.company_id.currency_id.id)

    @api.depends('product_id','order_id')
    def _compute_planned_amount(self):
        for line in self:
            budget_amount = 0
            account_id = False
            product_id = line.product_id
            if product_id:
                date_planned = line.date_planned.date()
                if product_id.property_account_expense_id:
                    account_id = product_id.property_account_expense_id
                elif product_id.categ_id.property_account_expense_categ_id:
                    account_id = product_id.categ_id.property_account_expense_categ_id
            # budget_id = self.env['budgetextension.budget']
            if account_id:
                domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                ('state', '=', 2), ('account_id', '=', account_id.id)]
                budget_id = self.env['budgetextension.budget'].search(domain)
                if budget_id:
                    budget_amount = budget_id.sudo().planned_amount
                else:
                    if line.order_id.capex_group_id:
                        group_name = line.order_id.capex_group_id.name
                    else:
                        group_name = self.env['x.capex.group'].sudo().search([('account_ids','in',account_id.id)],limit=1).name
                    domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                    budget_id = self.env['x_capex'].sudo().search(domain)
                    if budget_id:
                        budget_amount = budget_id.x_budget_total_total*-1
            line.planned_amount = budget_amount

    @api.depends('product_id','order_id')
    def _compute_practical_amount(self):
        for line in self:
            actual_amount = 0
            account_id = False
            product_id = line.product_id
            if product_id:
                date_planned = line.date_planned.date()
                if product_id.property_account_expense_id:
                    account_id = product_id.property_account_expense_id
                elif product_id.categ_id.property_account_expense_categ_id:
                    account_id = product_id.categ_id.property_account_expense_categ_id
            budget_id = self.env['budgetextension.budget']
            if account_id:
                domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                ('state', '=', 2), ('account_id', '=', account_id.id)]
                budget_id = self.env['budgetextension.budget'].sudo().search(domain)
                if budget_id:
                    actual_amount = budget_id.sudo().practical_amount
                else:
                    if line.order_id.capex_group_id:
                        group_name = line.order_id.capex_group_id.name
                    else:
                        group_name = self.env['x.capex.group'].sudo().search([('account_ids','in',account_id.id)],limit=1).name
                    domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                    budget_id = self.env['x_capex'].sudo().search(domain)
                    if budget_id:
                        actual_amount = budget_id.x_total_total*-1
            line.practical_amount = actual_amount

    @api.depends('planned_amount', 'practical_amount')
    def _compute_difference(self):
        for line in self:
            line.amount_difference = line.planned_amount - line.practical_amount


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    x_studio_attachment = fields.Binary(string="Attachment", attachment=True)
    x_studio_attachment2 = fields.Binary(string="Attachment 2", attachment=True)
    x_studio_attachment3 = fields.Binary(string="Attachment 3", attachment=True)
    x_studio_attachment_4 = fields.Binary(string="Attachment 4", attachment=True)
    x_studio_attachment_5 = fields.Binary(string="Attachment 5", attachment=True)
    p_type = fields.Selection([
        ('inventory','Inventory'),
        ('consumable','Consumable'),
        ('service','Service')],string='Type')
    x_studio_inv_status = fields.Selection([
        ('draft','Draft'),
        ('open','Open'),
        ('in_payment','In Payment'),
        ('paid','Paid'),
        ('cancel','Canelled')],string='INV  Status', related='order_line.invoice_lines.move_id.state', store=True)

    def check_two_step(self):
        is_two_step = False
        avoid_rules_accounts = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.avoid_rules_accounts', [])
        for rec_details in self.order_line:
            # two steps for PD
            if str(rec_details.product_id.id) in avoid_rules_accounts.split(","):
                return True
            else:
                is_two_step = False
        return is_two_step

    def button_cancel_greg(self):
        for order in self:
            for inv in order.invoice_ids:
                if inv and inv.state not in ('cancel', 'draft'):
                    raise UserError(_("Unable to cancel this purchase order. You must first cancel the related vendor bills."))

        self.write({'state': 'cancel', 'mail_reminder_confirmed': False})

    @api.model
    def create(self, vals):
        gty_comp = self.env['res.company'].sudo().search([('name','ilike','GTY')])
        if len(self.env.companies.ids)>1 or self.env.companies[0].id!=gty_comp.id:
            raise UserError(_("Please change your current company to '"+(gty_comp.name or '')+"'"))
        result = super(PurchaseOrder, self).create(vals)
        if result.amount_total<=0:
            raise UserError("Your requested amount cannot be ZERO. \nPlease input Unit Price and Quantity.")
        if result.check_two_step()==True:
            director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
            if result.x_studio_approver.id!=director_id:
                result.x_studio_approver=director_id
        return result

    def write(self, values):
        result = super(PurchaseOrder, self).write(values)
        for rec in self:
            if rec.amount_total<=0:
                raise UserError("Your requested amount cannot be ZERO. \nPlease input Unit Price and Quantity.")
    #     if self.check_two_step()==True:
    #         director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
    #         if self.x_studio_approver.id!=director_id:
    #             self.x_studio_approver=director_id
        return result

    def budget_account_dict(self, account_id, price_subtotal, budget_account_dict, account_analytic,product_id=False,date_from=False,date_to=False):
        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id
            rate = currency_id.with_context(date=self.date_order)
            price_subtotal = currency_id._convert(price_subtotal, self.company_id.currency_id, self.company_id, self.date_order or fields.Date.today())
        
        #check pending PO amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('order_id.id','!=',self.id),('order_id.state','!=','cancel'),('order_id.invoice_count','=',0),('company_id','=',self.company_id.id)]
        if self.capex_group_id:
            domain += [('order_id.capex_group_id','=',self.capex_group_id.id)]
        po_lines = self.env['purchase.order.line'].sudo().search(domain)
        for line in po_lines:
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
        if self.capex_group_id:
            domain += [('capex_group_id','=',self.capex_group_id.id)]
        lines = self.env['employee.advance.expense'].sudo().search(domain)
        for line in lines:
            subtotal = line.total_amount_expense
            if line.currency_id and line.company_id and line.currency_id != line.company_id.currency_id:
                currency_id = line.currency_id
                rate = currency_id.with_context(date=line.request_date)
                subtotal = currency_id._convert(subtotal, line.company_id.currency_id, line.company_id, line.request_date or fields.Date.today())
            _logger.debug('####################################################### Other Advance amount')
            _logger.debug('%s, %s, %s'%(line.id, line.name,subtotal))
            price_subtotal += subtotal

        #check other Reimbursement amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('advance_line_id.state','in',('draft','confirm','approved_hr_manager','paid')),('advance_line_id.company_id','=',self.company_id.id)]
        if self.capex_group_id:
            domain += [('advance_line_id.capex_group_id','=',self.capex_group_id.id)]
        lines = self.env['advance.expense.line'].sudo().search(domain)
        for line in lines:
            subtotal = line.total_amount
            if line.advance_line_id.currency_id and line.advance_line_id.company_id and line.advance_line_id.currency_id != line.advance_line_id.company_id.currency_id:
                currency_id = line.advance_line_id.currency_id
                rate = currency_id.with_context(date=line.advance_line_id.request_date)
                subtotal = currency_id._convert(subtotal, line.advance_line_id.company_id.currency_id, line.advance_line_id.company_id, line.advance_line_id.request_date or fields.Date.today())
            _logger.debug('####################################################### Other Reimbursement amount')
            _logger.debug('%s, %s, %s'%(line.advance_line_id.id,line.advance_line_id.name,subtotal))
            price_subtotal += subtotal

        #check pending Invoice
        domain = [('account_id.code','=',account_id.code),('move_id.state','=','draft'),('date','>=',date_from),('date','<=',date_to)]
        if self.capex_group_id:
            domain += [('capex_group_id','=',self.capex_group_id.id)]
        aml_lines = self.env['account.move.line'].sudo().search(domain)
        for line in aml_lines:
            subtotal = line.debit-line.credit
            _logger.debug('####################################################### Other Invoice amount')
            _logger.debug('%s, %s, %s'%(line.move_id.id,line.move_id.name,subtotal))
            price_subtotal += subtotal
        
        if account_id.id in account_analytic:
            budget_account_dict[account_id.id].append(price_subtotal)
        else:
            account_analytic.append(account_id.id)
            budget_account_dict[account_id.id] = [price_subtotal]
        return {'budget_account_dict': budget_account_dict,
                'account_analytic': account_analytic,
                'account_id': account_id}

    def accouting_budget_warning(self, order, order_line, warning_msg, budget_account_dict, account_analytic, update=False):
        for line in order_line:
            # if not update:
            product_id = line.product_id
            date_planned = line.date_planned.date()
            if line.taxes_id:
                vals = self.calculate_tax(line)
                price_subtotal = vals['price_subtotal']
            else:
                price_subtotal = (line.price_unit * line.product_qty)
            account_id = False
            asset = False
            if product_id.property_account_expense_id:
                account_id = product_id.property_account_expense_id
            elif product_id.categ_id.property_account_expense_categ_id:
                account_id = product_id.categ_id.property_account_expense_categ_id
            # elif product_id.asset_category_id:
            #     account_id = product_id.asset_category_id.account_asset_id
            #     asset = True
            if account_id:
                if not account_id.no_budget:
                    if account_id.workinprocess and not line.order_id.capex_group_id:
                        raise UserError('You will need to put Capex Group for this account code.')
                    elif not account_id.workinprocess and line.order_id.capex_group_id:
                        raise UserError('You will not need to add Capex Group for this account code. Please remove Capex Group.')

                    domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                    ('state', '=', 2), ('account_id.code', '=', account_id.code)] # including ISYA
                    budget_id = self.env['budgetextension.budget'].sudo().search(domain)
                    if budget_id:
                        practical_amount = sum(budget_id.mapped('practical_amount')) or 0
                        planned_amount = sum(budget_id.mapped('planned_amount')) or 0
                        vals = order.budget_account_dict(account_id, price_subtotal, budget_account_dict, account_analytic,product_id=product_id.id,date_from=budget_id[0].start_date,date_to=budget_id[0].end_date)
                        total_price = (sum(budget_account_dict.get(account_id.id)))
                        
                        if ( practical_amount + total_price) > planned_amount:
                            warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % product_id.name)
                    else: # asset/capex budget
                        if line.order_id.capex_group_id:
                            group_name = line.order_id.capex_group_id.name
                        else:
                            group_name = self.env['x.capex.group'].search([('account_ids','in',account_id.id)],limit=1).name
                        domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                        budget_id = self.env['x_capex'].search(domain)
                        if budget_id:
                            budget_amount = budget_id.x_budget_total_total*-1
                            actual_amount = budget_id.x_total_total*-1
                            vals = order.budget_account_dict(account_id, price_subtotal, budget_account_dict, account_analytic,product_id=product_id.id,date_from=budget_id[0].x_start_date,date_to=budget_id[0].x_end_date)
                            total_price = (sum(budget_account_dict.get(account_id.id)))
                            
                            if (actual_amount + total_price) > budget_amount:
                                warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % product_id.name)                    
                        elif account_id.code.startswith("5") or account_id.name.startswith("5"):
                            raise UserError("Please contact Odoo team to choose the correct account code. \n %s doesn't have the current fiscal year budget"%(product_id.display_name))
            else:
                raise UserError("%s is not an expense type. \n Please contact Odoo team to choose the correct account code."%(product_id.display_name))
        if warning_msg:
            raise UserError(_(''.join(warning_msg)))

    def button_confirm(self):
        for order in self:
            if order.state not in ['draft', 'sent']:
                continue
            order._add_supplier_to_product()
            # Deal with double validation process
            is_two_step = False
            if order.company_id.po_double_validation == 'one_step'\
                    or (order.company_id.po_double_validation == 'two_step'
                        and order.amount_total < self.env.user.company_id.currency_id._convert(
                            order.company_id.po_double_validation_amount, order.currency_id, order.company_id, order.date_order or fields.Date.today()))\
                    or order.user_has_groups('purchase.group_purchase_manager'):
                avoid_rules_accounts = self.env['ir.config_parameter'].sudo().get_param(
                    'mt_isy.avoid_rules_accounts', [])
                avoid_rules_accounts_social_event = self.env['ir.config_parameter'].sudo().get_param(
                    'mt_isy.avoid_rules_accounts_social_event', [])
                avoid_rules_accounts_social_event = avoid_rules_accounts_social_event.split(",")
                for rec_details in order.order_line:
                    # two steps for PD
                    if str(rec_details.product_id.id) in avoid_rules_accounts.split(","):
                        is_two_step = True
                        break
                    elif rec_details.product_id.id in self.env['product.product'].search(['|',('default_code','in',avoid_rules_accounts_social_event),('name','in',avoid_rules_accounts_social_event)]).ids:
                        is_two_step = True
                        break
                    else: # one step
                        is_two_step = False
            else: # two steps for Double Validation
                is_two_step = True
            
            if is_two_step:
                order.write({'state': 'to approve'})
            else:
                order.button_approve()
        return True

    def _prepare_invoice(self):
        """Prepare the dict of values to create the new invoice for a purchase order.
        """
        self.ensure_one()
        move_type = self._context.get('default_move_type', 'in_invoice')
        journal = self.env['account.journal'].search([('type', '=', 'purchase'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_('Please define an accounting purchase journal for the company %s (%s).') % (self.company_id.name, self.company_id.id))

        partner_invoice_id = self.partner_id.address_get(['invoice'])['invoice']
        partner_bank_id = self.partner_id.commercial_partner_id.bank_ids.filtered_domain(['|', ('company_id', '=', False), ('company_id', '=', self.company_id.id)])[:1]
        invoice_vals = {
            'ref': self.partner_ref or '',
            'move_type': move_type,
            'narration': self.notes,
            'currency_id': self.currency_id.id,
            'invoice_user_id': self.user_id and self.user_id.id or self.env.user.id,
            'partner_id': partner_invoice_id,
            #'fiscal_position_id': (self.fiscal_position_id or self.fiscal_position_id.get_fiscal_position(partner_invoice_id)).id,
            'payment_reference': self.partner_ref or '',
            'partner_bank_id': partner_bank_id.id,
            'invoice_origin': self.name,
            'invoice_payment_term_id': self.payment_term_id.id,
            'invoice_line_ids': [],
            'company_id': self.company_id.id,
            'purchase_id':self.id,
            'invoice_date':fields.Date.today(),
            'journal_id':journal.id,
            'x_studio_field_hrbLx':2,
        }
        return invoice_vals

    def action_create_invoice(self):
        """Create the invoice associated to the PO.
        """
        precision = self.env['decimal.precision'].precision_get('Product Unit of Measure')

        # 1) Prepare invoice vals and clean-up the section lines
        invoice_vals_list = []
        sequence = 10
        for order in self:
            order.order_line._compute_qty_invoiced()
            if order.invoice_status != 'to invoice':
                continue

            order = order.with_company(order.company_id)
            pending_section = None
            # Invoice values.
            invoice_vals = order._prepare_invoice()
            # Invoice line values (keep only necessary sections).
            for line in order.order_line:
                if line.display_type == 'line_section':
                    pending_section = line
                    continue
                if not float_is_zero(line.qty_to_invoice, precision_digits=precision):
                    if pending_section:
                        line_vals = pending_section._prepare_account_move_line()
                        line_vals.update({'sequence': sequence,'capex_group_id':order.capex_group_id.id})
                        invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                        sequence += 1
                        pending_section = None
                    line_vals = line._prepare_account_move_line()
                    line_vals.update({'sequence': sequence,'capex_group_id':order.capex_group_id.id})
                    invoice_vals['invoice_line_ids'].append((0, 0, line_vals))
                    sequence += 1
            invoice_vals_list.append(invoice_vals)

        if not invoice_vals_list:
            raise UserError(_('There is no invoiceable line. If a product has a control policy based on received quantity, please make sure that a quantity has been received.'))

        # 2) group by (company_id, partner_id, currency_id) for batch creation
        new_invoice_vals_list = []
        for grouping_keys, invoices in groupby(invoice_vals_list, key=lambda x: (x.get('company_id'), x.get('partner_id'), x.get('currency_id'))):
            origins = set()
            payment_refs = set()
            refs = set()
            ref_invoice_vals = None
            for invoice_vals in invoices:
                if not ref_invoice_vals:
                    ref_invoice_vals = invoice_vals
                else:
                    ref_invoice_vals['invoice_line_ids'] += invoice_vals['invoice_line_ids']
                origins.add(invoice_vals['invoice_origin'])
                payment_refs.add(invoice_vals['payment_reference'])
                refs.add(invoice_vals['ref'])
            ref_invoice_vals.update({
                'ref': ', '.join(refs)[:2000],
                'invoice_origin': ', '.join(origins),
                'payment_reference': len(payment_refs) == 1 and payment_refs.pop() or False,
            })
            new_invoice_vals_list.append(ref_invoice_vals)
        invoice_vals_list = new_invoice_vals_list

        # 3) Create invoices.
        moves = self.env['account.move']
        AccountMove = self.env['account.move'].with_context(default_move_type='in_invoice')
        for vals in invoice_vals_list:
            moves |= AccountMove.with_company(vals['company_id']).create(vals)

        # 4) Some moves might actually be refunds: convert them if the total amount is negative
        # We do this after the moves have been created since we need taxes, etc. to know if the total
        # is actually negative or not
        #moves.filtered(lambda m: m.currency_id.round(m.amount_total) < 0).action_switch_invoice_into_refund_credit_note()
        return self.action_view_invoice(moves)


# class AccountInvoice(models.Model):
#     _inherit = "account.invoice"

#     def action_invoice_paid(self):
#         # lots of duplicate calls to action_invoice_paid, so we remove those already paid
#         to_pay_invoices = self.filtered(lambda inv: inv.state != 'paid')
#         if to_pay_invoices.filtered(lambda inv: inv.state not in ('open', 'in_payment')):
#             raise UserError(_('Invoice must be validated in order to set it to register payment.'))
#         if to_pay_invoices.filtered(lambda inv: not inv.reconciled):
#             raise UserError(_('You cannot pay an invoice which is partially paid. You need to reconcile payment entries first.'))

#         for invoice in to_pay_invoices:
#             if any([move.journal_id.post_at_bank_rec and move.state == 'draft' for move in invoice.payment_move_line_ids.mapped('move_id')]):
#                 invoice.write({'state': 'in_payment'})
#             else:
#                 obj_po_invoices = self.search([('origin','=',invoice.origin)])
#                 obj_po = self.env['purchase.order'].search([('name','=',invoice.origin)])
#                 if obj_po_invoices and len(obj_po_invoices) > 1:
#                     obj_po_invoice -= invoice
#                     if not obj_po_invoices:
#                         obj_po.write({'payment_status': 'paid'})
#                     else:
#                         for  opi in obj_po_invoices:
#                             if opi.state != 'paid':
#                                 obj_po.write({'payment_status': 'partial'})
#                 invoice.write({'state': 'paid'})
