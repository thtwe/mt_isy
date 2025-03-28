# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, float_is_zero
import odoo.addons.decimal_precision as dp
from odoo.tools.misc import format_date
import logging
_logger = logging.getLogger(__name__)
from odoo.osv import expression

class HolidaysRequest(models.Model):
    _inherit = 'hr.leave'

    @api.depends('employee_id','holiday_status_id')
    def compute_current_leave_balance(self):
        # for rec in self:
        #     holiday_status_id = self.env['hr.leave.type'].search([('name','ilike','Personal Leave'),('active','=',True)],limit=1, order='id desc')
        #     mapped_days = holiday_status_id.get_employees_days((rec.employee_id | rec.employee_ids).ids)
        #     if rec.employee_id:
        #         leave_days = mapped_days[rec.employee_id.id][holiday_status_id.id]
        #         rec.current_personal_balance = leave_days.get('virtual_remaining_leaves') or 0
        #     else:
        #         rec.current_personal_balance = 0
        for rec in self:
            holiday_status_id = self.env['hr.leave.type'].search([('name','ilike','Personal Leave'),('active','=',True)],limit=1, order='id desc')
            if rec.employee_id and holiday_status_id:
                # Step 1: Calculate the Allocated Leave from the hr.leave.allocation model
                allocation_records = self.env['hr.leave.allocation'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('holiday_status_id', '=', holiday_status_id.id),
                    ('state', '=', 'validate')  # Only consider validated allocations
                ])

                total_allocated = sum(allocation.number_of_days for allocation in allocation_records)
                
                # Step 2: Calculate the Taken Leave from the hr.leave model
                leave_records = self.env['hr.leave'].search([
                    ('employee_id', '=', rec.employee_id.id),
                    ('holiday_status_id', '=', rec.holiday_status_id.id),
                    ('state', '=', 'validate')  # Only consider validated leaves
                ])

                total_taken = sum(leave.number_of_days for leave in leave_records)

                # Calculate remaining balance: Allocated - Taken
                rec.current_personal_balance = total_allocated - total_taken
            else:
                rec.current_personal_balance = 0

    leave_balance = fields.Float(string="Leave Balance", store=True)
    current_personal_balance = fields.Float(string="Personal Leave",compute='compute_current_leave_balance')
    # x_current_leave_balance = fields.Float('')
    activity_ids = fields.One2many(
        'mail.activity', 'res_id', 'Activities',
        auto_join=True,
        groups="",) # remove access right

    holiday_status_id = fields.Many2one(
        "hr.leave.type", compute='_compute_from_employee_id', store=True, string="Leave Type", required=True, readonly=False,
        states={'cancel': [('readonly', True)], 'refuse': [('readonly', True)], 'validate1': [('readonly', True)], 'validate': [('readonly', True)]},
        domain=['|', ('requires_allocation', '=', 'no'), ('has_valid_allocation', '=', True)])
    employee_id = fields.Many2one(
        'hr.employee', compute='', store=True, string='Employee', index=True, readonly=False, ondelete="restrict",
        states={'cancel': [('readonly', True)], 'refuse': [('readonly', True)], 'validate1': [('readonly', True)], 'validate': [('readonly', True)]},
        tracking=True,default=lambda x: x.env['hr.employee'].search([('user_id','=',x.env.user.id)]).id)

    @api.depends('employee_ids')
    def _compute_from_employee_ids(self):
        for holiday in self:
            # if len(holiday.employee_ids) == 1:
            #     holiday.employee_id = holiday.employee_ids[0]._origin
            # else:
            #     holiday.employee_id = False
            holiday.multi_employee = (len(holiday.employee_ids) > 1)

    @api.depends('holiday_type','employee_id')
    def _compute_from_holiday_type(self):
        for holiday in self:
            if holiday.holiday_type == 'employee':
                # if not holiday.employee_ids:
                #     # This handles the case where a request is made with only the employee_id
                #     # but does not need to be recomputed on employee_id changes
                holiday.employee_ids = holiday.employee_id or self.env.user.employee_id
                holiday.mode_company_id = False
                holiday.category_id = False
            elif holiday.holiday_type == 'company':
                holiday.employee_ids = False
                if not holiday.mode_company_id:
                    holiday.mode_company_id = self.env.company.id
                holiday.category_id = False
            elif holiday.holiday_type == 'department':
                holiday.employee_ids = False
                holiday.mode_company_id = False
                holiday.category_id = False
            elif holiday.holiday_type == 'category':
                holiday.employee_ids = False
                holiday.mode_company_id = False
            else:
                holiday.employee_ids = self.env.context.get('default_employee_id') or holiday.employee_id or self.env.user.employee_id

    @api.onchange('holiday_status_id')
    def _onchange_holiday_status_id(self):
        self.request_unit_half = False
        self.request_unit_hours = False
        #self.request_unit_custom = False
        if self.holiday_status_id.requires_allocation == "yes":
            self.leave_balance = self.holiday_status_id.virtual_remaining_leaves
        elif self.holiday_status_id.accumulated_leave:
            self.leave_balance = self.employee_id.accumulated_leave
        elif self.holiday_status_id.unpaid_accumulated_leave:
            self.leave_balance = self.employee_id.unpaid_accumulated_leave
        else:
            self.leave_balance = self.holiday_status_id.virtual_remaining_leaves

    @api.model
    def create(self, values):
        """ Override to avoid automatic logging of creation """
        obj_leave_type = self.env['hr.leave.type'].search([('id', '=', values.get('holiday_status_id'))])
        obj_employee = self.env['hr.employee'].sudo().search([('id','=', values.get('employee_id'))])
        if obj_employee.user_id.login!='director@isyedu.org' and not obj_employee.parent_id:
            raise UserError("%s doesn't have Supervisor in the system. Please contact to Ei Pan Phyu<ephyu@isyedu.org>."%(obj_employee.name))
        if obj_leave_type.accumulated_leave:
            if obj_employee.unpaid_accumulated_leave > 0:
                raise ValidationError(_("Please take Unpaid Accumulated Leave Type First."))
        #     values['leave_balance'] = obj_employee.accumulated_leave
        # elif obj_leave_type.unpaid_accumulated_leave:
        #     values['leave_balance'] = obj_employee.unpaid_accumulated_leave
        # else:
        #     values['leave_balance'] = obj_leave_type.virtual_remaining_leaves
        holiday = super(HolidaysRequest, self.with_context(mail_create_nolog=True, mail_create_nosubscribe=True)).create(values)
        return holiday

    def activity_update(self):
        # not to send odoo default email
        return True
    
    @api.depends('employee_ids')
    def _compute_from_employee_ids(self):
        for holiday in self:
            # if len(holiday.employee_ids) == 1:
            #     holiday.employee_id = holiday.employee_ids[0]._origin
            # else:
            #     holiday.employee_id = False
            holiday.multi_employee = (len(holiday.employee_ids) > 1)

    @api.constrains('state', 'number_of_days', 'holiday_status_id')
    def _check_holidays(self):
        remaining_leave_map = {}
        for holiday in self:
            # Skip the check if there is no employee or holiday status
            if not holiday.employee_id or not holiday.holiday_status_id:
                continue

            # Calculate the remaining leaves for the employee and the specific leave type
            remaining_leave_map = self._get_remaining_leave_for_employees(
                holiday.employee_id, holiday.holiday_status_id)
            if holiday.holiday_type != 'employee' or holiday.holiday_status_id.requires_allocation == 'no':
                if holiday.holiday_status_id.accumulated_leave and holiday.employee_id.accumulated_leave <= 0:
                    raise ValidationError(_('The number of remaining time off is not sufficient for this time off type.'))
                elif holiday.holiday_status_id.unpaid_accumulated_leave and holiday.employee_id.unpaid_accumulated_leave <= 0:
                    raise ValidationError(_('The number of remaining time off is not sufficient for this time off type.'))
                else:
                    continue
            
            # Now validate the remaining leave balance for the employee
            if holiday.employee_id:
                remaining_leaves = remaining_leave_map.get(holiday.employee_id.id, 0)
                if remaining_leaves < self.number_of_days:
                    raise ValidationError(_('The number of remaining time off is not sufficient for this time off type.\n'
                                            'Please also check the time off waiting for validation.'))
            else:
                # Check for multiple employees
                unallocated_employees = []
                for employee in holiday.employee_ids:
                    remaining_leaves = remaining_leave_map.get(employee.id, 0)
                    if remaining_leaves < self.number_of_days:
                        unallocated_employees.append(employee.name)
                if unallocated_employees:
                    raise ValidationError(_('The number of remaining time off is not sufficient for this time off type.\n'
                                            'Please also check the time off waiting for validation.') +
                                        _('The employees that lack allocation days are:\n%s' % (', '.join(unallocated_employees))))

    def _get_remaining_leave_for_employees(self, employee, holiday_status):
        # Get all the allocations for the given holiday status
        allocations = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', holiday_status.id),
            ('state', '=', 'validate')  # Only consider validated allocations
        ])

        allocated_days = sum(allocation.number_of_days for allocation in allocations)

        # Get all the taken leave records for the given holiday status
        taken_leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('holiday_status_id', '=', holiday_status.id),
            ('state', '=', 'validate')  # Only consider validated leaves
        ])

        taken_days = sum(leave.number_of_days for leave in taken_leaves)

        remaining_leave = allocated_days - taken_days
        return {employee.id: remaining_leave}

    def action_approve(self):
        if self.employee_id.id and self.x_studio_approver_2 and self.x_studio_approver_2.user_id.id != self.env.user.id and self.env.user.login not in ('director@isyedu.org','odooadmin@isyedu.org'):
            raise UserError("You are not allowed to approve. %s is approver for this request."%(self.x_studio_approver_2.name))
        return super(HolidaysRequest, self).action_approve()

    def action_validate(self):
        if self.employee_id.id and self.env.user.login not in ('director@isyedu.org','odooadmin@isyedu.org'):
            raise UserError("You are not allowed to approve it. Director is the second approver.")
        return super(HolidaysRequest, self).action_validate()


class HolidaysAllocation(models.Model):
    _inherit = 'hr.leave.allocation'

    def _default_holiday_status_id(self):
        if self.user_has_groups('hr_holidays.group_hr_holidays_user'):
            domain = [('has_valid_allocation', '=', True), ('requires_allocation', '=', 'yes')]
        else:
            domain = [('has_valid_allocation', '=', True), ('requires_allocation', '=', 'yes'), ('employee_requests', '=', 'yes')]
        return self.env['hr.leave.type'].search(domain, limit=1)

    def _domain_holiday_status_id(self):
        if self.user_has_groups('hr_holidays.group_hr_holidays_user'):
            return [('requires_allocation', '=', 'yes')]
        return [('employee_requests', '=', 'yes')]

    holiday_status_id = fields.Many2one(
        "hr.leave.type", compute='_compute_holiday_status_id', store=True, string="Leave Type", required=True, readonly=False,
        states={'cancel': [('readonly', True)], 'refuse': [('readonly', True)], 'validate1': [('readonly', True)], 'validate': [('readonly', True)]},
        domain=_domain_holiday_status_id,
        default=_default_holiday_status_id)

class ResPartner(models.Model):
    _inherit = "res.partner"

    def name_get(self):
        result = []
        for rec in self:
            if ';' in rec.name and rec.student_number:
                lname, fname = rec.name.split(";")
                name = fname.lstrip() + " " + lname
                result.append((rec.id, name))
            else:
                name = rec._get_name()
                result.append((rec.id, name))
        return result

class AdvanceExpenseClearanceLine(models.Model):
    _name = "advance.expense.clearance.line"
    _description = "Advance Expense Clearance Line"

    @api.depends('unit_amount', 'quantity')
    def _compute_total_line_expense(self):
        for rec in self:
            amount_line = rec.unit_amount * rec.quantity
            rec.total_amount = amount_line

    product_id = fields.Many2one('product.product', string='Expense')
    product_uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True, readonly=True, states={'draft': [('readonly', False)], 'refused': [('readonly', False)]}, default=lambda self: self.env['uom.uom'].search([], limit=1, order='id'))
    unit_amount = fields.Float(string='Unit Price', required=True, digits=dp.get_precision('Product Price'))
    quantity = fields.Float(required=True, digits=dp.get_precision('Product Unit of Measure'), default=1)
    description = fields.Char(string='Description', required=True)
    total_amount = fields.Float(string='Subtotal', compute='_compute_total_line_expense', digits=dp.get_precision('Account'))
    currency_id = fields.Many2one('res.currency', string='Currency', related='advance_id.currency_id', readonly=True, store=True)
    #expense_line_ids = fields.One2many('hr.expense', 'sheet_id', string='Expense Lines', copy=False)
    advance_id = fields.Many2one('employee.advance.expense', string="Advance Expense Report")
    employee_id = fields.Many2one('hr.employee', required=True, string="Employee", related='advance_id.employee_id')
    name = fields.Char(
        string='Number',
        related='advance_id.name',
        readonly=1,
    )
    state = fields.Selection(
        related='advance_id.state',
    )
    reambursment = fields.Boolean(
        string='Reimbursement',
        default=False,
    )
    cls_move_id = fields.Many2one('account.move', string='Cls JE', readonly=True)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for rec in self:
            rec.description = rec.product_id.name
            if rec.advance_id.company_id.currency_id != rec.advance_id.currency_id:
                # amount = rec.advance_id.company_id.currency_id.compute(rec.product_id.standard_price, rec.advance_id.currency_id)
                amount = rec.advance_id.company_id.currency_id._convert(
                from_amount=rec.product_id.standard_price,
                to_currency=rec.advance_id.currency_id,
                company=self.env.company,
                date=fields.Date.today()
                )
                rec.unit_amount = amount
            else:
                rec.unit_amount = rec.product_id.standard_price

class EmployeeAdvanceExpense(models.Model):
    _inherit = 'employee.advance.expense'
    _description = "Employee Advance Expense"

    state = fields.Selection(selection_add=[('payable', 'Payable'), ('partial', 'Partial'), ('cleared', 'Cleared')])
    advance_expense_clearance_line_ids = fields.One2many('advance.expense.clearance.line', 'advance_id', string='Advance Expenses Lines', copy=False)

    cls_journal_id = fields.Many2one('account.journal', string='Clearance Journal')
    account_clearance_date = fields.Date(string='Final Clearance Date',
                        readonly=True, copy=False)
    clearnce_account_by_id = fields.Many2one('res.users', string='Make Clearance By', readonly=True, copy=False)
    cash_cleared_amount = fields.Float(string='Cash Clearance Amount', digits=dp.get_precision('Account'))
    adv_exp_type = fields.Selection([('advance', 'Advance'), ('expense', 'Expense')])
    exp_journal_id = fields.Many2one('account.journal', string='Expense Journal')
    settlement_date = fields.Date(string='Settlement Date',
                        readonly=True, copy=False)
    settlement_account_by_id = fields.Many2one('res.users', string='Make Settlement By', readonly=True, copy=False)
    settlement_move_id = fields.Many2one('account.move', string="Settlement Entry", readonly=True, copy=False)
    state_adv = fields.Selection(related='state')
    state_exp = fields.Selection(related='state')
    cash_clearance_date = fields.Date(string="Cash Clearance Date", copy=False)
    account_id = fields.Many2one('account.account', string='Asset Account',related='')
    hr_done_date = fields.Date(string='Done Date', readonly=True, copy=False)

    x_studio_attachment = fields.Binary(string="Attachment", attachment=True)
    x_studio_attachment2 = fields.Binary(string="Attachment 2", attachment=True)
    x_studio_attachment3 = fields.Binary(string="Attachment 3", attachment=True)
    x_studio_attachment_4 = fields.Binary(string="Attachment 4", attachment=True)
    x_studio_attachment_5 = fields.Binary(string="Attachment 5", attachment=True)
    is_asset = fields.Boolean(string="Is Asset(?)", default=False)
    x_studio_to_approve = fields.Many2one('res.users', string='To Approve')
    x_studio_field_b6lRX = fields.Many2one(related='x_studio_to_approve', string='To Approve')


    both_approval = fields.Boolean(default=False, string="Both Approval", help="It is true then user who has approval accounts can able to approve without caring the rules below 1000 and above 1000.")
    p_type = fields.Selection([
        ('inventory','Inventory'),
        ('consumable','Consumable'),
        ('service','Service')],string='Type')

    def get_apprv_hr_manager(self):
        total_amount = self.total_amount_expense
        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id
            rate = currency_id.with_context(date=self.request_date)
            total_amount = currency_id._convert(self.total_amount_expense, self.company_id.currency_id, self.company_id, self.request_date or fields.Date.today())
        # over $1000 MMK
        if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and self.currency_id.name=='MMK' and self.total_amount_expense>2100000:
            raise UserError(_('You do not have permission to approve this request.'))
        # over $1000 USD
        if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and self.currency_id.name=='USD' and total_amount > 999.99:
            raise UserError(_('You do not have permission to approve this request.'))
        # Salary Advance
        if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and self.salary_advance:
            raise UserError(_('You do not have permission to approve this request.'))
        # Professional Development and Social Event
        if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and self.both_approval:
            raise UserError(_('You do not have permission to approve this request.'))
        

        # if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and total_amount > 999.99:
        #     raise UserError(_('You do not have permission to approve this request.'))
        # if self.env.user.id != 191 and not self.env.user.has_group('base.group_system') and self.salary_advance:
        #     raise UserError(_('You do not have permission to approve this request.'))
        
        
        self.state = 'approved_hr_manager'
        self.hr_validate_date = time.strftime('%Y-%m-%d')
        self.hr_manager_by_id = self.env.user.id

    def budget_account_dict(self, account_id, price_subtotal, budget_account_dict, account_analytic,product_id=False,date_from=False,date_to=False):
        if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
            currency_id = self.currency_id
            rate = currency_id.with_context(date=self.request_date)
            price_subtotal = currency_id._convert(price_subtotal, self.company_id.currency_id, self.company_id, self.request_date or fields.Date.today())
        
        #check other PO amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('order_id.state','!=','cancel'),('order_id.invoice_count','=',0),('company_id','=',self.company_id.id)]
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

        #check other Advance amount
        # domain = [('x_studio_anticipated_account_code','=',product_id),('id','!=',self.id),('state','in',('draft','confirm','approved_hr_manager','paid')),('company_id','=',self.company_id.id)]
        domain = [('x_studio_anticipated_account_code.property_account_expense_id','=',account_id.id),('id','!=',self.id),('state','not in',('cancel','rejected','cleared')),('company_id','=',self.company_id.id)]
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
            _logger.debug('%s, %s, %s'%(line.id,line.name,subtotal))
            price_subtotal += subtotal

        #check other Reimbursement amount
        domain = [('product_id.property_account_expense_id','=',account_id.id),('advance_line_id.id','!=',self.id),('advance_line_id.state','in',('draft','confirm','approved_hr_manager','paid')),('advance_line_id.company_id','=',self.company_id.id)]
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
            if order.adv_exp_type == 'advance':
                product_id = order.x_studio_anticipated_account_code
            else:
                product_id = line.product_id
            date_planned = order.request_date
            price_subtotal = order.total_amount_expense
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
                    if account_id.workinprocess and not order.capex_group_id:
                        raise UserError('You will need to put Capex Group for this account code.')
                    elif not account_id.workinprocess and order.capex_group_id:
                        raise UserError('You will not need to add Capex Group for this account code. Please remove Capex Group.')
                    
                    domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                    ('state', '=', 2), ('account_id.code', '=', account_id.code)] # including ISYA
                    budget_id = self.env['budgetextension.budget'].sudo().search(domain)
                    if budget_id:
                        practical_amount = sum(budget_id.mapped('practical_amount')) or 0
                        planned_amount = sum(budget_id.mapped('planned_amount')) or 0
                        vals = order.budget_account_dict(account_id, price_subtotal, budget_account_dict, account_analytic,product_id=product_id.id,date_from=budget_id[0].start_date,date_to=budget_id[0].end_date)
                        total_price = (sum(budget_account_dict.get(account_id.id)))
                        if (practical_amount + total_price) > planned_amount:
                            warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % product_id.name)
                    else: # asset/capex budget
                        if order.capex_group_id:
                            group_name = order.capex_group_id.name
                        else:
                            group_name = self.env['x.capex.group'].sudo().search([('account_ids','in',account_id.id)],limit=1).name
                        domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                        budget_id = self.env['x_capex'].sudo().search(domain)
                        if budget_id:
                            budget_amount = budget_id.sudo().x_budget_total_total*-1
                            actual_amount = budget_id.sudo().x_total_total*-1
                            vals = order.budget_account_dict(account_id, price_subtotal, budget_account_dict, account_analytic,product_id=product_id.id,date_from=budget_id[0].x_start_date,date_to=budget_id[0].x_end_date)
                            total_price = (sum(budget_account_dict.get(account_id.id)))
                            if (actual_amount + total_price) > budget_amount:
                                warning_msg.append('\"The budget limit for account code (%s) is exceeded. \n Please contact the Director or COO\". \n' % product_id.name)                    
                        elif account_id.code.startswith("5") or account_id.name.startswith("5"):
                            raise UserError("Please contact Odoo team to choose the correct account code.\n %s doesn't have the current fiscal year budget"%(product_id.display_name))
            else:
                raise UserError("%s is not an expense type. \n Please contact Odoo team to choose the correct account code."%(product_id.display_name))
        if warning_msg:
            raise UserError(_(''.join(warning_msg)))
    

    @api.model
    def create(self, values):
        gty_comp = self.env['res.company'].sudo().search([('name','ilike','GTY')])
        if len(self.env.companies)>1 or self.env.companies[0].id!=gty_comp.id:
            raise UserError(_("Please change your current company to '"+(gty_comp.name or '')+"'"))

        avoid_rules_accounts = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.avoid_rules_accounts', [])
        avoid_rules_accounts_social_event = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.avoid_rules_accounts_social_event', [])
        avoid_rules_accounts_social_event = avoid_rules_accounts_social_event.split(",")
        if values['adv_exp_type'] == 'advance':
            if str(values['x_studio_anticipated_account_code']) in avoid_rules_accounts.split(","):
                values['both_approval'] = True
                director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
                values['x_studio_to_approve']=director_id
                values['x_studio_field_b6lRX']=director_id
            elif values['x_studio_anticipated_account_code'] in self.env['product.product'].search(['|',('default_code','in',avoid_rules_accounts_social_event),('name','in',avoid_rules_accounts_social_event)]).ids:
                values['both_approval'] = True
                values['x_type_name'] = 'Social Event'
                director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
                if self.env.user.id==director_id:
                    coo_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.COO', 1737))
                    values['x_studio_to_approve']=coo_id
                    values['x_studio_field_b6lRX']=coo_id
            else:
                values['both_approval'] = False
        elif values['adv_exp_type'] == 'expense':
            for rec_details in values['advance_expense_line_ids']:
                if str(rec_details[2]['product_id']) in avoid_rules_accounts.split(","):
                    values['both_approval'] = True
                    director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
                    values['x_studio_to_approve']=director_id
                    values['x_studio_field_b6lRX']=director_id
                    break
                elif rec_details[2]['product_id'] in self.env['product.product'].search(['|',('default_code','in',avoid_rules_accounts_social_event),('name','in',avoid_rules_accounts_social_event)]).ids:
                    values['both_approval'] = True
                    values['x_type_name'] = 'Social Event'
                    director_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.director', 191))
                    if self.env.user.id==director_id:
                        coo_id = int(self.env['ir.config_parameter'].sudo().get_param('isy.COO', 1737))
                        values['x_studio_to_approve']=coo_id
                        values['x_studio_field_b6lRX']=coo_id
                    break
                else:
                   values['both_approval'] = False
        
        advance_expenses = super(EmployeeAdvanceExpense, self).create(values)
        if advance_expenses.total_amount_expense<=0:
            raise UserError("Your requested amount cannot be ZERO. \nPlease input Unit Price and Quantity.")
        warning_msg = []
        budget_account_dict = {}
        account_analytic = []   
        self.accouting_budget_warning(advance_expenses, advance_expenses.advance_expense_line_ids, warning_msg, budget_account_dict, account_analytic, update=False)
        return advance_expenses

    def write(self, values):
        if values and 'x_studio_anticipated_account_code' in values.keys() and self.env.user.login not in ('director@isyedu.org','odooadmin@isyedu.org'):
            raise UserError("You cannot change Anticipated Account Code on this state. Please contact to Administrator.")
        if values and values.get('advance_expense_line_ids') and len(values['advance_expense_line_ids'][0] or [])>2 \
                and 'product_id' in values['advance_expense_line_ids'][0][2].keys() and self.env.user.login not in ('director@isyedu.org','odooadmin@isyedu.org'):
            raise UserError("You cannot change Anticipated Account Code on this state. Please contact to Administrator.")
        res = super(EmployeeAdvanceExpense, self).write(values)
        for rec in self:
            if rec.total_amount_expense<=0:
                raise UserError("Your requested amount cannot be ZERO. \nPlease input Unit Price and Quantity.")
            warning_msg = []
            budget_account_dict = {}
            account_analytic = []
            if 'advance_expense_line_ids' in values:  
                    rec.accouting_budget_warning(rec, rec.advance_expense_line_ids, warning_msg, budget_account_dict, account_analytic, update=True)
        return res

    # def _compute_both_approval(self):
    #     for rec in self:
    #         avoid_rules_accounts = self.env['ir.config_parameter'].sudo().get_param(
    #             'mt_isy.avoid_rules_accounts', [])
    #         if rec.adv_exp_type == 'advance':
    #             if str(rec.x_studio_anticipated_account_code.id) in avoid_rules_accounts.split(","):
    #                 rec.both_approval = True
    #             else:
    #                 rec.both_approval = False
    #         elif rec.adv_exp_type == 'expense':
    #             for rec_details in rec.advance_expense_line_ids:
    #                 if str(rec_details.product_id.id) in avoid_rules_accounts.split(","):
    #                     rec.both_approval = True
    #                     break
    #                 else:
    #                     rec.both_approval = False


    @api.constrains('advance_expense_line_ids')
    def check_lines_count(self):
        if len(self.advance_expense_line_ids) > 1:
            raise ValidationError(_("Advance Expense Line only allow to add one line."))

    @api.onchange('partner_id')
    def onchange_partner_id(self):
        if self.partner_id and self.adv_exp_type == 'advance':
            self.account_id = self.partner_id.property_account_receivable_id.id
        else:
            self.account_id = self.partner_id.property_account_payable_id.id

    @api.model
    def _reminder_for_clearance(self):
        for rec in self.search([('state', '=', 'done'), ('salary_advance', '=', False), ('adv_exp_type', '=', 'advance')]):
            no_of_days = abs((fields.Date.today() - rec.account_validate_date).days)
            if no_of_days > 30:
                template = self.env.ref('mt_isy.clearance_reminder')
                self.env['mail.template'].browse(template.id).send_mail(rec.id)
                print("----------------------- 30 Days after for " + rec.employee_id.name)

    def days_between(d1, d2):
        #d1 = datetime.strptime(d1, "%Y-%m-%d")
        #d2 = datetime.strptime(d2, "%Y-%m-%d")
        return abs((d2 - d1).days)

    def make_settlement(self):
        vals = {
            'amount': self.total_amount_expense,
            'currency_id': self.currency_id.id
        }
        res_id = self.env['expense.settlement'].create(vals)
        wizard_form = self.env.ref('mt_isy.view_isy_expense_settlement', False)

        return {
                    'name': 'Settlement',
                    'type': 'ir.actions.act_window',
                    'view_type': 'form',
                    'view_mode': 'form',
                    'res_model': 'expense.settlement',
                    'res_id': res_id.id,
                    'views': [(wizard_form.id, 'form')],
                    'target': 'new',
                    'domain': [],
                    'context': {}
        }

    def get_done(self):
        if self.adv_exp_type == 'advance':
            if (self.env.user.has_group('account.group_business_manager')):
                if self.journal_id.type == 'cash':
                    raise UserError(_('You can not make this payment!'))
            state = 'done'
        else:
            state = 'payable'
        if not self.move_id:
            if self.currency_id.id != self.env.user.company_id.currency_id.id:
                today_rate = self.env['res.currency.rate'].search([('currency_id', '=', self.currency_id.id), ('name', '=',  str(fields.date.today()))])
                if not today_rate:
                    raise ValidationError(_("There has no currecy rate for today."))

            created_moves = self.env['account.move']
            prec = self.env['decimal.precision'].precision_get('Account')
            if not self.journal_id:
                raise UserError(_("No Credit account found for the Journal, please configure one.") % (self.journal_id))
            if not self.journal_id:
                raise UserError(_("No Debit account found for the account, please configure one.") % (self.account_id))
            for line in self:
                #             category_id = line.asset_id.category_id
                adv_exp_date = fields.Date.context_today(self)
                if line.company_id != self.env.user.company_id:
                    raise UserError(_("You are doing from different company."))
                company_currency = line.company_id.currency_id
                current_currency = line.currency_id
                #amount = current_currency.compute(line.total_amount_expense, company_currency)
                amount = current_currency._convert(
                    from_amount=line.total_amount_expense,
                    to_currency=company_currency,
                    company=self.env.company,
                    date=adv_exp_date
                )
                _logger.info(f"Converted Amount: {amount}, Original: {line.total_amount_expense}, Currency: {current_currency.name}")

                ref = line.name
                prec = company_currency.rounding  # Use correct currency rounding
                ref = line.name
                if self.adv_exp_type == 'advance':
                    move_line_credit = {
                        'name': ref,
                        'account_id': line.journal_id.default_account_id.id,
                        # 'debit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
                        # 'credit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
                        'debit': 0.0,
                        'credit': amount,
                        'journal_id': line.journal_id.id,
                        'partner_id': line.partner_id.id,
                        #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
                        #'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        # 'amount_currency': company_currency != current_currency and - 1.0 * line.total_amount_expense or 0.0,
                        'amount_currency': line.total_amount_expense * -1.0,
                        #'amount_currency': -amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else amount,
                    }
                    move_line_debit = {
                        'name': ref,
                        'account_id': line.account_id.id,
                        # 'credit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
                        # 'debit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
                        'credit': 0.0,
                        'debit': amount,
                        'journal_id': line.journal_id.id,
                        'partner_id': line.partner_id.id,
                        #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                        #'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        # 'amount_currency': company_currency != current_currency and line.total_amount_expense or 0.0,
                        'amount_currency': line.total_amount_expense,
                    }
                    move_vals = {
                        'ref': line.name,
                        'date': adv_exp_date or False,
                        'journal_id': line.journal_id.id,
                        'narration': line.reason_for_advance,
                        'line_ids': [(0, 0, move_line_debit), (0, 0, move_line_credit)],
                    }
                else:
                    move_line_list = []
                    move_line_credit = (0, 0, {
                        'name': ref,
                        'account_id': line.account_id.id,
                        # 'debit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
                        # 'credit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
                        'debit': 0.0,
                        'credit': amount,
                        'journal_id': line.exp_journal_id.id,
                        'partner_id': line.partner_id.id,
                        #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
                        #'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                        # 'amount_currency': company_currency != current_currency and - 1.0 * line.total_amount_expense or 0.0,
                        'amount_currency': line.total_amount_expense * -1.0,
                    })
                    move_line_list.append(move_line_credit)
                    for adv_exp_line in line.advance_expense_line_ids:
                        #debit_amount = current_currency.compute(adv_exp_line.total_amount, company_currency)
                        debit_amount = current_currency._convert(
                            from_amount=adv_exp_line.total_amount,
                            to_currency=company_currency,
                            company=self.env.company,
                            date=adv_exp_date
                        )
                        move_line_debit = (0, 0, {
                            'name': ref,
                            'account_id': adv_exp_line.product_id.property_account_expense_id.id,
                            # 'credit': 0.0 if float_compare(debit_amount, 0.0, precision_digits=prec) > 0 else -debit_amount,
                            # 'debit': debit_amount if float_compare(debit_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                            'credit': 0.0,
                            'debit': debit_amount,
                            'journal_id': line.exp_journal_id.id,
                            'partner_id': line.partner_id.id,
                            #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                            #'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                            # 'amount_currency': company_currency != current_currency and line.total_amount_expense or 0.0,
                            'amount_currency': line.total_amount_expense,
                            'capex_group_id': self.capex_group_id.id
                        })
                        move_line_list.append(move_line_debit)
                    move_vals = {
                        'ref': line.name,
                        'date': adv_exp_date or False,
                        'journal_id': line.exp_journal_id.id,
                        'narration': line.reason_for_advance,
                        'line_ids': move_line_list,
                    }
                _logger.info(f"Creating journal entry with values: {move_vals}")
                move = self.env['account.move'].create(move_vals)

                line.write({'move_id': move.id,
                            'state': state,
                            'account_validate_date': time.strftime('%Y-%m-%d'),
                            'account_by_id': line.env.user.id,
                            'is_paid': True})
                created_moves |= move
            return [x.id for x in created_moves]

        #Journal Entry exists for old data and update state, hr_done_date, account_validate_date
        else:
            for line in self:
                line.write({'state': state,
                            'hr_done_date': line.account_validate_date,
                            'account_validate_date': time.strftime('%Y-%m-%d'),
                            })
                if line.move_id.state == 'draft':
                    line.move_id.write({
                        'date': time.strftime('%Y-%m-%d'),
                    })

            # if post_move and created_moves:
            #     created_moves.filtered(lambda m: any(m.asset_depreciation_ids.mapped('asset_id.category_id.open_asset'))).post()


    def get_confirm(self):
        if not self.advance_expense_line_ids:
            raise UserError(_('Please add some advance expense lines.'))
        else:
            if self.x_studio_to_approve and self.x_studio_to_approve.id!=self.env.user.id:
                if self.env.user.login!='odooadmin@isyedu.org':
                    raise UserError("%s is approver for this request. You are not allowed to approve this."%(self.x_studio_to_approve.name))
            if self.adv_exp_type == 'advance':
                if len(self.advance_expense_line_ids) > 1:
                    raise ValidationError(_("Advance only allow to add one record for Advance Expense Lines."))
                check_misc = self.advance_expense_line_ids.filtered(lambda x: x.product_id.x_studio_misc == False)
                if len(check_misc) > 0:
                    raise ValidationError(_("Please choose Product for Advance Only!"))
            if self.adv_exp_type == 'expense' and len(self.advance_expense_line_ids) > 1:
                raise ValidationError(_("Reimbursement only allow to add one record for Advance Expense Lines."))
            total_amount = self.total_amount_expense

            if self.adv_exp_type == 'advance':
                self.name = self.env['ir.sequence'].next_by_code('employee.advance.expense')
            else:
                self.name = self.env['ir.sequence'].next_by_code('employee.advance.expense.reimbursement')

            if self.currency_id and self.company_id and self.currency_id != self.company_id.currency_id:
                currency_id = self.currency_id
                rate = currency_id.with_context(date=self.request_date)
                total_amount = currency_id._convert(self.total_amount_expense, self.company_id.currency_id, self.company_id, self.request_date or fields.Date.today())
            # if(total_amount > 250000 and self.env.user.login != 'director@isyedu.org'):
            #     raise UserError(_('Cannot confirm this advance as it exceeds $250,000 limit.'))
            # else:
            self.state = 'confirm'
            self.confirm_date = time.strftime('%Y-%m-%d')
            self.confirm_by_id = self.env.user.id

    # Done State key is 'paid'.
    # override reverse process with get_done and action_sheet_move_advance
    # no journal entry when click done
    def action_sheet_move_advance(self):
        self.write({
            'state': 'paid',
            'hr_done_date': time.strftime('%Y-%m-%d'),
        })
        if self.adv_exp_type!='advance':
            self.get_done()

    def make_clearance(self):
        if not self.cash_cleared_amount and not self.advance_expense_clearance_line_ids and self.salary_advance:
            raise UserError(_("Salary Advance Clearance will make clearance from payslip!"))
        if not self.advance_expense_clearance_line_ids:
            raise ValidationError(_("Please fill clearance lines."))
        #amount that is for bank and local control but can be different exchange rate.
        clear_amount = sum(result.total_amount for result in self.advance_expense_clearance_line_ids.search([('cls_move_id', '=', False), ('advance_id', '=', self.id)]))
        if not self.cash_cleared_amount and round(clear_amount, 2) != self.total_amount_expense:
            raise ValidationError(_("Please fill Cash Clearance Amount"))
        if not self.salary_advance:
            if round(clear_amount + self.cash_cleared_amount, 2) != self.total_amount_expense:
                raise ValidationError(_("Clearance lines total amount and cash clearance amount are different."))
            move_vals = self.get_normal_move_vals(clear_amount)
        else:
            move_vals = self.get_salary_adv_move_vals(clear_amount)

        move = self.env['account.move'].create(move_vals)
        #move.post()
        clearance_total_amount = sum(result.total_amount for result in self.advance_expense_clearance_line_ids.search([('advance_id', '=', self.id)]))
        state = 'partial' if self.total_amount_expense != round(clearance_total_amount + self.cash_cleared_amount, 2) else 'cleared'
        self.write({
                    'state': state,
                    'account_clearance_date': '' if state != 'cleared' else time.strftime('%Y-%m-%d'),
                    'clearnce_account_by_id': self.env.user.id,
                    })
        self.advance_expense_clearance_line_ids.search([('cls_move_id', '=', False), ('advance_id', '=', self.id)]).write({'cls_move_id': move.id})
        #created_moves |= move

        # if post_move and created_moves:
        #     created_moves.filtered(lambda m: any(m.asset_depreciation_ids.mapped('asset_id.category_id.open_asset'))).post()
        #return [x.id for x in created_moves]

    def get_salary_adv_move_vals(self, clear_amount):
        created_moves = self.env['account.move']
        prec = self.env['decimal.precision'].precision_get('Account')
        if not self.advance_expense_clearance_line_ids:
            raise UserError(_("Please add advance clearance line"))

        vals = []
        adv_cls_date = self.cash_clearance_date or fields.Date.context_today(self)
        company_currency = self.company_id.currency_id
        current_currency = self.currency_id

        #usd amount
        amount = current_currency.with_context({'date': self.account_validate_date}).compute(clear_amount, company_currency)

        ref = self.name
        move_line_credit = (0, 0, {
            'name': ref,
            'account_id': self.account_id.id,
            'debit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
            'credit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'journal_id': self.cls_journal_id.id,
            'partner_id': self.partner_id.id,
            #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
            # 'amount_currency': company_currency != current_currency and - 1.0 * clear_amount or 0.0,
            'amount_currency': clear_amount * -1.0,
        })
        vals.append(move_line_credit)

        #convert mmk to usd
        cash_debit_amount = current_currency.with_context({'date': self.cash_clearance_date}).compute(clear_amount, company_currency)
        cash_move_line_debit = (0, 0, {
            'name': ref,
            'account_id': self.journal_id.default_account_id.id,
            'credit': 0.0 if float_compare(cash_debit_amount, 0.0, precision_digits=prec) > 0 else -cash_debit_amount,
            'debit': cash_debit_amount if float_compare(cash_debit_amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'journal_id': self.cls_journal_id.id,
            'partner_id': self.partner_id.id,
            #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
            # 'amount_currency': company_currency != current_currency and clear_amount or 0.0,
            'amount_currency': clear_amount,
        })
        vals.append(cash_move_line_debit)

        #diff amount with usd
        diff_amount = amount - cash_debit_amount

        if diff_amount != 0:
            print("need to make exchange adjustment")
            account_id = self.company_id.currency_exchange_journal_id.default_account_id.id
            #convert usd to mmk
            diff_amount_currency = company_currency.with_context({'date': self.cash_clearance_date}).compute(diff_amount, current_currency)
            gain_loss_diff = (0, 0, {
                'name': ref,
                'account_id': account_id,
                'credit': 0.0 if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else -diff_amount,
                'debit': diff_amount if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                'journal_id': self.cls_journal_id.id,
                'partner_id': self.partner_id.id,
                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                # 'amount_currency': company_currency != current_currency and diff_amount_currency or 0.0,
                'amount_currency': diff_amount_currency,
            })
            vals.append(gain_loss_diff)

        move_vals = {
            'ref': str(self.name) + "[Salary Advance Clearance]",
            'date': adv_cls_date or False,
            'journal_id': self.cls_journal_id.id,
            'narration': self.reason_for_advance,
            'line_ids': vals,
        }
        return move_vals

    def get_normal_move_vals(self, clear_amount):
        created_moves = self.env['account.move']
        prec = self.env['decimal.precision'].precision_get('Account')
        if not self.journal_id:
            raise UserError(_("No Credit account found for the Journal, please configure one.") % (self.journal_id))
        if not self.journal_id:
            raise UserError(_("No Debit account found for the account, please configure one.") % (self.account_id))
        if not self.advance_expense_clearance_line_ids:
            raise UserError(_("Please add advance clearance line"))

        vals = []
        adv_cls_date = self.cash_clearance_date or fields.Date.context_today(self)
        company_currency = self.company_id.currency_id
        current_currency = self.currency_id
        #usd amount
        # amount = current_currency.with_context({'date': self.account_validate_date}).compute(self.total_amount_expense, company_currency)
        amount = current_currency._convert(
            from_amount=self.total_amount_expense,
            to_currency=company_currency,
            company=self.env.company,
            date=self.account_validate_date
        )
        ref = self.name
        move_line_credit = (0, 0, {
            'name': ref,
            'account_id': self.account_id.id,
            'debit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
            'credit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'journal_id': self.cls_journal_id.id,
            'partner_id': self.partner_id.id,
            #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
            # 'amount_currency': company_currency != current_currency and - 1.0 * self.total_amount_expense or 0.0,
            'amount_currency': self.total_amount_expense * -1.0,
        })
        vals.append(move_line_credit)

        counter_amount = 0
        counter_amount_currency = 0
        for line in self.advance_expense_clearance_line_ids:
            #             category_id = line.asset_id.category_id
            #usd amount
            # line_amount = current_currency.with_context({'date': self.cash_clearance_date}).compute(line.total_amount, company_currency)
            line_amount = current_currency._convert(
                from_amount=line.total_amount,
                to_currency=company_currency,
                company=self.env.company,
                date=self.cash_clearance_date
            )
            #mmk amount
            counter_amount_currency += line.total_amount
            #usd amount
            counter_amount += line_amount
            move_line_debit = (0, 0, {
                'name': ref,
                'account_id': line.product_id.property_account_expense_id.id or line.product_id.categ_id.property_account_expense_categ_id.id or False,
                'credit': 0.0 if float_compare(line_amount, 0.0, precision_digits=prec) > 0 else -line_amount,
                'debit': line_amount if float_compare(line_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                'journal_id': line.advance_id.cls_journal_id.id,
                'partner_id': line.advance_id.partner_id.id,
                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                # 'amount_currency': company_currency != current_currency and line.total_amount or 0.0,
                'amount_currency': line.total_amount,
                'capex_group_id': self.capex_group_id.id,
            })
            vals.append(move_line_debit)

        cash_debit_amount = 0
        if self.total_amount_expense > counter_amount_currency:
            #mmk amount
            cash_debit_amount_before = self.cash_cleared_amount  # self.total_amount_expense - counter_amount_currency
            #convert mmk to usd
            # cash_debit_amount = current_currency.with_context({'date': self.cash_clearance_date}).compute(cash_debit_amount_before, company_currency)
            cash_debit_amount = current_currency._convert(
                from_amount=cash_debit_amount_before,
                to_currency=company_currency,
                company=self.env.company,
                date=self.cash_clearance_date
            )
            cash_move_line_debit = (0, 0, {
                'name': ref,
                'account_id': self.journal_id.default_account_id.id,
                'credit': 0.0 if float_compare(cash_debit_amount, 0.0, precision_digits=prec) > 0 else -cash_debit_amount,
                'debit': cash_debit_amount if float_compare(cash_debit_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                'journal_id': self.cls_journal_id.id,
                'partner_id': self.partner_id.id,
                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                # 'amount_currency': company_currency != current_currency and cash_debit_amount_before or 0.0,
                'amount_currency': cash_debit_amount_before,
            })
            vals.append(cash_move_line_debit)
        #diff amount with usd
        diff_amount = round(amount, 2) - round(cash_debit_amount + counter_amount, 2)

        if diff_amount:
            print("need to make exchange adjustment")
            account_id = self.company_id.currency_exchange_journal_id.default_account_id.id
            #convert usd to mmk
            # diff_amount_currency = company_currency.with_context({'date': self.cash_clearance_date}).compute(diff_amount, current_currency)
            diff_amount_currency = company_currency._convert(
                from_amount=diff_amount,
                to_currency=current_currency,
                company=self.env.company,
                date=self.cash_clearance_date
            )
            gain_loss_diff = (0, 0, {
                'name': ref,
                'account_id': account_id,
                'credit': 0.0 if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else -diff_amount,
                'debit': diff_amount if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                'journal_id': self.cls_journal_id.id,
                'partner_id': self.partner_id.id,
                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                # 'amount_currency': company_currency != current_currency and diff_amount_currency or 0.0,
                'amount_currency': diff_amount_currency,
            })
            vals.append(gain_loss_diff)

        move_vals = {
            'ref': str(self.name) + "[Clearance]",
            'date': adv_cls_date or False,
            'journal_id': self.cls_journal_id.id,
            'narration': self.reason_for_advance,
            'line_ids': vals,
        }
        return move_vals


class AccountFiscalYear(models.Model):
    _inherit = "account.fiscal.year"

    active = fields.Boolean(string="Active(?)", default=True)
    ccm_budget = fields.Boolean(string="CCM Budget(?)", default=False)


# class AccountInvoice(models.Model):
#     _inherit = "account.invoice"

#     @api.depends('residual', 'amount_total')
#     def _compute_paid_amount(self):
#         for rec in self:
#             if rec.residual and rec.amount_total:
#                 rec.paid_amount_total = rec.amount_total - rec.residual

#     paid_amount_total = fields.Monetary(string='Total Paid',
#         store=True, readonly=True, compute='_compute_paid_amount')

#     @api.onchange('x_studio_vendor_pick_up')
#     def _onchange_vendor_pickup(self):
#         for rec in self:
#             _logger.debug('$$$$$$$$$$$$$4 Vendor Pickup %s'%(rec.x_studio_vendor_pick_up))
#             _logger.debug('$$$$$$$$$$$$$4 Vendor Pickup %s'%(rec.purchase_id.x_studio_pick_up_at_cashier))
#             #if rec.purchase_id.x_studio_pick_up_at_cashier:
#             if rec.x_studio_vendor_pick_up:
#                 payment_method = self.env['account.payment.method'].search([('name','=','Cash'),('payment_type','=','outbound')],limit=1,order='id desc')
#             else:
#                 if rec.purchase_id.x_studio_pick_up_at_cashier:
#                     payment_method = self.env['account.payment.method'].search([('name','=','Cash'),('payment_type','=','outbound')],limit=1,order='id desc')
#                 else:
#                     payment_method = self.env['account.payment.method'].search([('name','=','Electronic'),('payment_type','=','outbound')],limit=1,order='id desc')
#             rec.x_studio_field_hrbLx = payment_method

class ResUsers(models.Model):
    _inherit = "res.users"

    portal_inventory_user = fields.Boolean(string='Portal Inventory User', copy=True, default=False)
    portal_payslip_process_request_user = fields.Boolean(string="Portal Payroll Process Requestor", copy=True, default=False)
    portal_inventory_own = fields.Boolean(string="Portal Inventroy ( Own Items )", copy=True, default=False)

    # def _message_get_suggested_recipients(self):
    #     # recipients = super(ResUsers, self)._message_get_suggested_recipients()
    #     return []
    
class AdvanceExpenseLine(models.Model):
    _inherit = "advance.expense.line"

    adv_exp_type = fields.Selection(
        [('advance', 'Advance'), ('expense', 'Expense')], related="advance_line_id.adv_exp_type")
    practical_amount = fields.Float(compute='_compute_practical_amount', string='Practical Amount', digits=0)
    planned_amount = fields.Float(compute='_compute_planned_amount', string='Planned Amount', digits=0)
    amount_difference = fields.Float(compute='_compute_difference', string='Remaining Balance', digits=0)
    company_currency_id = fields.Many2one('res.currency','Company Currency',default=lambda self: self.env.user.company_id.currency_id.id)

    @api.model
    def default_get(self,fields):
        res = super(AdvanceExpenseLine, self).default_get(fields)
        if self._context.get('adv_exp_type') == 'expense':
            res.update({'product_id':False})
        return res

    @api.depends('product_id','advance_line_id')
    def _compute_planned_amount(self):
        for line in self:
            budget_amount = 0
            account_id = False
            if line.advance_line_id.adv_exp_type=='advance':
                product_id = line.advance_line_id.x_studio_anticipated_account_code
            else:
                product_id = line.product_id
            if product_id:
                date_planned = line.advance_line_id.request_date
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
                    if line.advance_line_id.capex_group_id:
                        group_name = line.advance_line_id.capex_group_id.name
                    else:
                        group_name = self.env['x.capex.group'].search([('account_ids','in',account_id.id)],limit=1).name
                    domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                    budget_id = self.env['x_capex'].search(domain)
                    if budget_id:
                        budget_amount = budget_id.x_budget_total_total*-1
            line.planned_amount = budget_amount

    @api.depends('product_id','advance_line_id')
    def _compute_practical_amount(self):
        for line in self:
            actual_amount = 0
            account_id = False
            if line.advance_line_id.adv_exp_type=='advance':
                product_id = line.advance_line_id.x_studio_anticipated_account_code
            else:
                product_id = line.product_id
            date_planned = line.advance_line_id.request_date
            if product_id.property_account_expense_id:
                account_id = product_id.property_account_expense_id
            elif product_id.categ_id.property_account_expense_categ_id:
                account_id = product_id.categ_id.property_account_expense_categ_id

            if account_id:
                domain = [('start_date', '<=', date_planned), ('end_date', '>=', date_planned),
                ('state', '=', 2), ('account_id', '=', account_id.id)]
                budget_id = self.env['budgetextension.budget'].search(domain)
                if budget_id:
                    actual_amount = budget_id.sudo().practical_amount
                else:
                    if line.advance_line_id.capex_group_id:
                        group_name = line.advance_line_id.capex_group_id.name
                    else:
                        group_name = self.env['x.capex.group'].search([('account_ids','in',account_id.id)],limit=1).name
                    domain = [('x_start_date', '<=', date_planned), ('x_end_date', '>=', date_planned),('x_name', '=', group_name)]
                    budget_id = self.env['x_capex'].search(domain)
                    if budget_id:
                        actual_amount = budget_id.x_total_total*-1
            line.practical_amount = actual_amount

    @api.depends('planned_amount', 'practical_amount')
    def _compute_difference(self):
        for line in self:
            line.amount_difference = line.planned_amount - line.practical_amount


class Employee(models.Model):
    _inherit = "hr.employee"

    @api.model
    def _lang_get(self):
        return self.env['res.lang'].get_installed()

    private_street = fields.Char(string="Private Street", groups=False)
    private_street2 = fields.Char(string="Private Street2", groups=False)
    private_city = fields.Char(string="Private City", groups=False)
    private_state_id = fields.Many2one(
        "res.country.state", string="Private State",
        domain="[('country_id', '=?', private_country_id)]",
        groups=False)
    private_zip = fields.Char(string="Private Zip", groups=False)
    private_country_id = fields.Many2one("res.country", string="Private Country", groups=False)
    private_phone = fields.Char(string="Private Phone", groups=False)
    private_email = fields.Char(string="Private Email", groups=False)
    lang = fields.Selection(selection=_lang_get, string="Lang", groups=False)
    country_id = fields.Many2one(
        'res.country', 'Nationality (Country)', groups=False, tracking=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], groups=False, tracking=True)
    marital = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('cohabitant', 'Legal Cohabitant'),
        ('widower', 'Widower'),
        ('divorced', 'Divorced')
    ], string='Marital Status', groups=False, default='single', tracking=True)
    spouse_complete_name = fields.Char(string="Spouse Complete Name", groups=False, tracking=True)
    spouse_birthdate = fields.Date(string="Spouse Birthdate", groups=False, tracking=True)
    children = fields.Integer(string='Number of Dependent Children', groups=False, tracking=True)
    place_of_birth = fields.Char('Place of Birth', groups=False, tracking=True)
    country_of_birth = fields.Many2one('res.country', string="Country of Birth", groups=False, tracking=True)
    birthday = fields.Date('Date of Birth', groups=False, tracking=True)
    ssnid = fields.Char('SSN No', help='Social Security Number', groups=False, tracking=True)
    sinid = fields.Char('SIN No', help='Social Insurance Number', groups=False, tracking=True)
    identification_id = fields.Char(string='Identification No', groups=False, tracking=True)
    passport_id = fields.Char('Passport No', groups=False, tracking=True)
    bank_account_id = fields.Many2one(
        'res.partner.bank', 'Bank Account Number',
        domain="[('partner_id', '=', work_contact_id), '|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        groups=False,
        tracking=True,
        help='Employee bank account to pay salaries')
    permit_no = fields.Char('Work Permit No', groups=False, tracking=True)
    visa_no = fields.Char('Visa No', groups=False, tracking=True)
    visa_expire = fields.Date('Visa Expiration Date', groups=False, tracking=True)
    work_permit_expiration_date = fields.Date('Work Permit Expiration Date', groups=False, tracking=True)
    has_work_permit = fields.Binary(string="Work Permit", groups=False)
    work_permit_scheduled_activity = fields.Boolean(default=False, groups=False)
    work_permit_name = fields.Char('work_permit_name', compute='_compute_work_permit_name')
    additional_note = fields.Text(string='Additional Note', groups=False, tracking=True)
    certificate = fields.Selection([
        ('graduate', 'Graduate'),
        ('bachelor', 'Bachelor'),
        ('master', 'Master'),
        ('doctor', 'Doctor'),
        ('other', 'Other'),
    ], 'Certificate Level', default='other', groups=False, tracking=True)
    study_field = fields.Char("Field of Study", groups=False, tracking=True)
    study_school = fields.Char("School", groups=False, tracking=True)
    emergency_contact = fields.Char("Contact Name", groups=False, tracking=True)
    emergency_phone = fields.Char("Contact Phone", groups=False, tracking=True)
    km_home_work = fields.Integer(string="Home-Work Distance", groups=False, tracking=True)
    employee_type = fields.Selection([
            ('employee', 'Employee'),
            ('student', 'Student'),
            ('trainee', 'Trainee'),
            ('contractor', 'Contractor'),
            ('freelance', 'Freelancer'),
        ], string='Employee Type', default='employee', required=True, groups=False,
        help="The employee type. Although the primary purpose may seem to categorize employees, this field has also an impact in the Contract History. Only Employee type is supposed to be under contract and will have a Contract History.")
    # employee in company
    category_ids = fields.Many2many(
        'hr.employee.category', 'employee_category_rel',
        'emp_id', 'category_id', groups=False,
        string='Tags')
    # misc
    notes = fields.Text('Notes', groups=False)
    barcode = fields.Char(string="Badge ID", help="ID used for employee identification.", groups=False, copy=False)
    pin = fields.Char(string="PIN", groups=False, copy=False,
        help="PIN used to Check In/Out in the Kiosk Mode of the Attendance application (if enabled in Configuration) and to change the cashier in the Point of Sale application.")
    departure_reason_id = fields.Many2one("hr.departure.reason", string="Departure Reason", groups=False,
                                          copy=False, tracking=True, ondelete='restrict')
    departure_description = fields.Html(string="Additional Information", groups=False, copy=False)
    departure_date = fields.Date(string="Departure Date", groups=False, copy=False, tracking=True)
    message_main_attachment_id = fields.Many2one(groups=False)
    id_card = fields.Binary(string="ID Card Copy", groups=False)
    driving_license = fields.Binary(string="Driving License", groups=False)
    private_car_plate = fields.Char(groups=False, help="If you have more than one car, just separate the plates by a space.")
 


    def _get_contracts(self, date_from, date_to, states=['open'], kanban_state=False):
        """
        Returns the contracts of the employee between date_from and date_to
        """
        state_domain = [('state', 'in', states)]
        if kanban_state:
            state_domain = expression.AND([state_domain, [('kanban_state', 'in', kanban_state)]])
        return self.env['hr.contract'].search(
            expression.AND([[('employee_id', 'in', self.ids)],
            state_domain,
            [('date_start', '<=', date_to),
                ('company_id','in',self.env.company.ids),
                '|',
                    ('date_end', '=', False),
                    ('date_end', '>=', date_from)]]))

    def _compute_contract_id(self):
        """ get the lastest contract """
        Contract = self.env['hr.contract']
        for employee in self:
            employee.contract_id = Contract.search([('employee_id', '=', employee.id),('company_id','in',self.env.company.ids)], order='date_start desc', limit=1)

    contract_id = fields.Many2one('hr.contract', string='Current Contract',compute='_compute_contract_id',
        groups=False,domain="[('company_id', '=', company_id)]", help='Current contract of the employee')
    is_scholarship_staff = fields.Boolean('Staff of Scholarship Student ?')

    def action_time_off_dashboard(self):
        return {
            'name': _('Time Off Dashboard'),
            'type': 'ir.actions.act_window',
            'res_model': 'hr.leave',
            'views': [[self.env.ref('hr_holidays.hr_leave_employee_view_dashboard').id, 'calendar'],[self.env.ref('mt_isy.hr_leave_tree_dashboard').id,'tree']],
            'domain': [('employee_id', 'in', self.ids)],
            'context': {
                'employee_id': self.ids,
                'search_default_group_type':1,
            },
        }
