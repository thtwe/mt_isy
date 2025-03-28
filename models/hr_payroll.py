# -*- coding: utf-8 -*-
from odoo.osv.expression import AND
from odoo.tools import format_date
import time
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, float_is_zero
import odoo.addons.decimal_precision as dp
import babel
from datetime import date, datetime, time, timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from pytz import timezone
import io
import base64
try:
    import xlsxwriter
except ImportError:
    _logger.debug('Can not import xlsxwriter`.')

import logging
_logger = logging.getLogger(__name__)

from odoo.tools import float_round, date_utils
from odoo.tools.misc import format_date
from odoo.tools.safe_eval import safe_eval


CASH_ALLOCATION_TYPE = [
    ('cash_usd', 'Amount in USD to be paid in USD cash'),
    ('local_bank_ks', 'Amount in USD to be converted into Kyat cash'),
    ('local_bank_mmk', 'Amount in USD to be deposited into Kyat bank account'),
    ('local_bank_$', 'Deposit into Local Bank (USD account)'),
    ('401_k', '401K Allocation'), 
    ('overseas_bank', 'Overseas Bank'),
    ('donation_uws','Donation to United World Schools'),
    ('donation_yas','Donation to Yangon Animal Shelter'),
    ('donation_clc','Donation to Care to the Least Center - CLC Family'),
    ('donation_chinthe','Donation to Chinthe Fund'),
    ('savings_for_education','College Education Saving Program Deduction'),
    ('gala_usd','Amount in USD to pay for ISY Gala Ticket(s) - $50 Each')
]


class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'

    company_id = fields.Many2one('res.company', string='Company', required=True,
        copy=False, default=lambda self: self.env.company.id)


class HrPayrollStructure(models.Model):
    _inherit = 'hr.payroll.structure'

    company_id = fields.Many2one('res.company', string='Company', required=True,
        copy=False, default=lambda self: self.env.company.id)
    rule_ids_topay = fields.Many2many('hr.salary.rule','hr_salary_stucture_rule','strut_id','rule_id',string='Rules to pay')
    

class HrSalaryRule(models.Model):
    _inherit = "hr.salary.rule"

    clear_with_advance = fields.Boolean("Clear with advance (?)", help="It makes clearance with advance for this employee according to this rule", default=False)
    settle_to_expense = fields.Boolean("Settle to Expense (?)", help="It makes settlement with expense for this employee according to this rule", default=False)
    company_id = fields.Many2one('res.company', string='Company', required=True,
        copy=False, default=lambda self: self.env.company.id)


class HrPayslip(models.Model):
    _inherit = 'hr.payslip'

    employee_id = fields.Many2one('hr.employee', string='Employee', required=True, readonly=True,
        states={'draft': [('readonly', False)], 'verify': [('readonly', False)]}, domain="[]")
    settlement_ids = fields.One2many('hr.payslip.settlement', 'payslip_id', string='settlement')
    company_id = fields.Many2one(
        'res.company', string='Company', copy=False, required=True,
        readonly=False,
        default=lambda self: self.env.company,
        states={'draft': [('readonly', False)], 'verify': [('readonly', False)]})
    
    @api.depends('employee_id')
    def _compute_company_id(self):
        for slip in self:
            slip.company_id = self.env.company.ids[0]

    def _get_payslip_lines(self):
        def _sum_salary_rule_category(localdict, category, amount):
            if category.parent_id:
                localdict = _sum_salary_rule_category(localdict, category.parent_id, amount)
            if 'categories' not in localdict:
                localdict['categories'] = {}
            localdict['categories'][category.code] = localdict['categories'].get(category.code, 0) + amount
            return localdict

        # self.ensure_one()
        # result = {}
        # rules_dict = {}
        # worked_days_dict = {line.code: line for line in self.worked_days_line_ids if line.code}
        # inputs_dict = {line.code: line for line in self.input_line_ids if line.code}

        # employee = self.employee_id
        # contract = self.contract_id

        # localdict = {
        #     **self._get_base_local_dict(),
        #     **{
        #         'categories': {},
        #         'rules': rules_dict,
        #         'payslip': self,
        #         'worked_days': self.worked_days_line_ids,
        #         'inputs': self.input_line_ids,
        #         'employee': employee,
        #         'contract': contract
        #     }
        # }
        result_list = []  # Stores results for multiple payslips

        for payslip in self:  # Loop over multiple payslips
            result = {}  # Each payslip has its own dictionary
            localdict = {  # Create a fresh dictionary for each payslip
                **payslip._get_base_local_dict(),
                'categories': {},
                'rules': {},
                'payslip': payslip,
                'worked_days': payslip.worked_days_line_ids,
                'inputs': payslip.input_line_ids,
                'employee': payslip.employee_id,
                'contract': payslip.contract_id
            }

        # for rule in sorted(self.struct_id.rule_ids, key=lambda x: x.sequence):
        for rule in sorted(self.contract_id.structure_type_id.struct_ids_topay.mapped('rule_ids_topay'), key=lambda x: x.sequence):
            localdict.update({
                'result': None,
                'result_qty': 1.0,
                'result_rate': 100})
            if rule._satisfy_condition(localdict):
                amount, qty, rate = rule._compute_rule(localdict)
                #check if there is already a rule computed with that code
                previous_amount = rule.code in localdict and localdict[rule.code] or 0.0
                #set/overwrite the amount computed for this rule in the localdict
                tot_rule = amount * qty * rate / 100.0
                localdict[rule.code] = tot_rule
                localdict['rules'][rule.code] = rule
                # sum the amount for its salary category
                localdict = _sum_salary_rule_category(localdict, rule.category_id, tot_rule - previous_amount)
                # create/overwrite the rule in the temporary results
                result[rule.code] = {
                    'sequence': rule.sequence,
                    'code': rule.code,
                    'name': rule.name,
                    #'note': rule.note,
                    'salary_rule_id': rule.id,
                    'contract_id': payslip.contract_id.id,
                    'employee_id': payslip.employee_id.id,
                    'amount': amount,
                    'quantity': qty,
                    'rate': rate,
                    'total': tot_rule,
                    'slip_id': payslip.id,
                }
        return result.values()

    def get_inputs(self, contracts, date_from, date_to):
        res = []

        struct_ids = contracts.structure_type_id.struct_ids_topay
        inputs = struct_ids.mapped('input_line_type_ids')

        for contract in contracts:
            for input in inputs:
                input_data = {
                    'input_type_id': input.id,
                    'name':input.name,
                    'code': input.code,
                    'contract_id': contract.id,
                }
                res += [(0,0,input_data)]
        return res

    @api.onchange('employee_id', 'date_from', 'date_to')
    @api.onchange('employee_id', 'struct_id', 'contract_id', 'date_from', 'date_to')
    def _onchange_employee(self):
        if (not self.employee_id) or (not self.date_from) or (not self.date_to):
            return

        employee = self.employee_id
        date_from = self.date_from
        date_to = self.date_to

        # self.company_id = employee.company_id
        if not self.contract_id or self.employee_id != self.contract_id.employee_id: # Add a default contract if not already defined
            contracts = employee._get_contracts(date_from, date_to)

            if not contracts or not contracts[0].structure_type_id.default_struct_id:
                self.contract_id = False
                self.struct_id = False
                return
            self.contract_id = contracts[0]
            self.struct_id = contracts[0].structure_type_id.default_struct_id

        payslip_name = self.struct_id.payslip_name or _('Salary Slip')
        self.name = '%s - %s - %s' % (payslip_name, self.employee_id.name or '', format_date(self.env, self.date_from, date_format="MMMM y"))

        if date_to > date_utils.end_of(fields.Date.today(), 'month'):
            self.warning_message = _("This payslip can be erroneous! Work entries may not be generated for the period from %s to %s." %
                (date_utils.add(date_utils.end_of(fields.Date.today(), 'month'), days=1), date_to))
        else:
            self.warning_message = False

        self.worked_days_line_ids = self._get_new_worked_days_lines()
        #computation of the salary input
        self.input_line_ids = [(6,0,{})]
        self.input_line_ids = self.get_inputs(self.contract_id, date_from, date_to)

        #MT Customized For Advance/Reimbursemnet auto input amount
        advance_clear_usd_amount = 0
        advance_clear_mmk_amount = 0

        reimbursement_settlement_usd_amount = 0
        reimbursement_settlement_mmk_amount = 0

        total_school_trip = 0
        total_other = 0
        total_tuition_fee = 0
        employee_type = 'expat' if 'Local' not in self.employee_id.sudo().category_ids.mapped('name') else 'local'
        
        # Expat->ISYA, Local->GTY
        if (employee_type=='expat' and not self.contract_id.company_id) or (employee_type=='local' and self.contract_id.company_id):
            advance_clear_amount_usd_objs = self.env['employee.advance.expense'].sudo().search([('partner_id', '=', self.employee_id.user_id.partner_id.id), ('state', 'in', ['done', 'partial', 'payable']), ('salary_advance', '=', True)])
            for advance_clear_amount_obj in advance_clear_amount_usd_objs:
                #ADVANCE USD AND MMK For INPUT LINES
                if advance_clear_amount_obj.adv_exp_type == 'advance':
                    if advance_clear_amount_obj.currency_id.name == 'USD':
                        if not advance_clear_amount_obj.advance_expense_clearance_line_ids:
                            advance_clear_usd_amount += advance_clear_amount_obj.total_amount_expense
                        else:
                            total_cleared_amount = 0
                            for cls_line in advance_clear_amount_obj.advance_expense_clearance_line_ids:
                                total_cleared_amount += cls_line.total_amount
                            advance_clear_usd_amount += advance_clear_amount_obj.total_amount_expense - total_cleared_amount
                    elif advance_clear_amount_obj.currency_id.name == 'MMK':
                        if not advance_clear_amount_obj.advance_expense_clearance_line_ids:
                            advance_clear_mmk_amount += advance_clear_amount_obj.total_amount_expense
                        else:
                            total_cleared_amount = 0
                            for cls_line in advance_clear_amount_obj.advance_expense_clearance_line_ids:
                                total_cleared_amount += cls_line.total_amount
                            advance_clear_mmk_amount += advance_clear_amount_obj.total_amount_expense - total_cleared_amount
                else:
                    if advance_clear_amount_obj.currency_id.name == 'USD':
                        reimbursement_settlement_usd_amount += advance_clear_amount_obj.total_amount_expense
                    elif advance_clear_amount_obj.currency_id.name == 'MMK':
                        reimbursement_settlement_mmk_amount += advance_clear_amount_obj.total_amount_expense

            #need to check hr payslip process request only allow one record per month
            #to modify again, they need to request Payroll Manger via email to cancel their record for this month request
            last_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.last_request_day', 20)
            previous_last_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.previous_last_request_day', 20)
            previous_lastday = ((self.date_from+relativedelta(months=-1)).replace(day=int(previous_last_day)))
            current_lastday = ((self.date_to).replace(day=int(last_day)))
            obj_payslip_process = self.env['hr.payslip.process.request'].sudo().search([('state','=','done'), ('request_employee_id', '=', self.employee_id.id),('requested_date','>',str(previous_lastday)+' 23:59:59'),('requested_date','<=',str(current_lastday)+' 23:59:59')])
            for obj_pp in obj_payslip_process:
                total_school_trip += obj_pp.total_school_trip_adjustment
                total_tuition_fee += obj_pp.total_tuition_fee_adjustment
                total_other += obj_pp.total_other_adjustment

        ASCD_RTST_DICT = {'ASCD_MMK': advance_clear_mmk_amount, 'ASCD_USD': advance_clear_usd_amount, 'RTST_MMK': reimbursement_settlement_mmk_amount, 'RTST_USD': reimbursement_settlement_usd_amount}
        TOTAL_ADJUSTMENT = {'OAJSLTP': total_school_trip, 'OAJTNFE': total_tuition_fee, 'OAJOR': total_other}

        if self.input_line_ids:
            for result in self.input_line_ids:
                if result.code in ASCD_RTST_DICT.keys():
                    if not result.amount:
                        result['amount'] = ASCD_RTST_DICT[result['code']]
                elif result.code in TOTAL_ADJUSTMENT.keys():
                    if not result.amount:
                        result['amount'] = TOTAL_ADJUSTMENT[result['code']]
        # else:
        #     for r in input_line_ids:
        #         if r['code'] in ASCD_RTST_DICT.keys():
        #             r['amount'] = ASCD_RTST_DICT[r['code']]
        #             input_lines += input_lines.new(r)
        #         elif r['code'] in TOTAL_ADJUSTMENT.keys():
        #             r['amount'] = TOTAL_ADJUSTMENT[r['code']]
        #             input_lines += input_lines.new(r)
        #         else:
        #             input_lines += input_lines.new(r)
        #     self.input_line_ids = input_lines
        return

    def compute_sheet(self):
        res = super(HrPayslip, self).compute_sheet()
        # for rec in self:
        #     rec._onchange_employee()
        return True

    def action_payslip_done(self):
        #res = super(HrPayslip, self).action_payslip_done()
        self.compute_sheet()

        for slip in self:
            line_ids = []
            debit_sum = 0.0
            credit_sum = 0.0
            date = slip.date or slip.date_to
            currency = slip.company_id.currency_id

            name = _('Payslip of %s') % (slip.employee_id.name)
            move_dict = {
                'narration': name,
                'ref': slip.number,
                'journal_id': slip.journal_id.id,
                'date': date,
            }
            adv_cls_list = []
            for line in slip.line_ids:
                debit_account_id = line.salary_rule_id.account_debit.id
                credit_account_id = line.salary_rule_id.account_credit.id

                if line.salary_rule_id.clear_with_advance and line.amount != 0:
                    #payslip advance dedution amount
                    payslip_adv_cls_amount = line.amount * -1 if line.amount < 0 else line.amount

                    base_currency_domain = [('currency_id', '=', slip.employee_id.company_id.currency_id.id), ('partner_id', '=', slip.employee_id.user_id.partner_id.id), ('state', 'in', ['done', 'partial']), ('salary_advance', '=', True), ('request_date', '<=', slip.date_to), ('adv_exp_type', '=', 'advance')]
                    obj_base_currency_advs = self.env['employee.advance.expense'].sudo().search(base_currency_domain)
                    if not slip.input_line_ids.filtered(lambda r: r.code == "ASCD_USD").amount:
                        obj_base_currency_advs = []
                    #get base currency advance amount
                    obj_bca_result = 0
                    over_condition = True
                    for obj_bca in obj_base_currency_advs:
                        if obj_bca.advance_expense_clearance_line_ids:
                            obj_bca_result += obj_bca.total_amount_expense - sum(result.total_amount for result in obj_bca.advance_expense_clearance_line_ids.search([('advance_id', '=', obj_bca.id)]))
                        else:
                            obj_bca_result += obj_bca.total_amount_expense

                        if obj_bca_result > slip.input_line_ids.filtered(lambda r: r.code == "ASCD_USD").amount:
                            #clearance done
                            if len(obj_base_currency_advs) == 1:
                                obj_bca_result = slip.input_line_ids.filtered(lambda r: r.code == "ASCD_USD").amount
                                adv_cls_list.append({'id': obj_bca, 'amount':obj_bca.total_amount_expense, 'amount_cls': obj_bca_result, 'description': line.salary_rule_id.name, 'state': 'partial'})
                            else:
                                amount_cls = payslip_adv_cls_amount - (obj_bca_result - obj_bca.total_amount_expense)
                                obj_bca_result = payslip_adv_cls_amount
                                if amount_cls == obj_bca.total_amount_expense:
                                    state = 'cleared'
                                else:
                                    state = 'partial'
                                adv_cls_list.append({'id': obj_bca,'amount':obj_bca.total_amount_expense, 'amount_cls': amount_cls, 'description': line.salary_rule_id.name, 'state': state})
                            #over_condition = False
                            #break
                        #full payment condition
                        elif obj_bca_result == payslip_adv_cls_amount:
                            over_condition = False
                            adv_cls_list.append({'id': obj_bca,'amount':obj_bca.total_amount_expense, 'amount_cls': obj_bca_result, 'description': line.salary_rule_id.name, 'state': 'cleared'})
                        #partial payment condition
                        else:
                            #store employee.advance.expense object
                            adv_cls_list.append({'id': obj_bca,'amount':obj_bca.total_amount_expense, 'amount_cls': obj_bca_result, 'description': line.salary_rule_id.name, 'state': 'cleared'})
                    #ForTestPurpose below comment
                    #obj_bca_result = 0
                    if debit_account_id and obj_bca_result:
                        debit_line = (0, 0, {
                            'name': line.name,
                            'partner_id': line._get_partner_id(credit_account=False),
                            'account_id': debit_account_id,
                            'journal_id': slip.journal_id.id,
                            'date': date,
                            'debit': obj_bca_result > 0.0 and obj_bca_result or 0.0,
                            'credit': obj_bca_result < 0.0 and -obj_bca_result or 0.0,
                            #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                            # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                        })
                        line_ids.append(debit_line)
                        debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']
                    if credit_account_id and obj_bca_result:
                        credit_line = (0, 0, {
                            'name': line.name,
                            'partner_id': line._get_partner_id(credit_account=True),
                            'account_id': credit_account_id,
                            'journal_id': slip.journal_id.id,
                            'date': date,
                            'debit': obj_bca_result < 0.0 and -obj_bca_result or 0.0,
                            'credit': obj_bca_result > 0.0 and obj_bca_result or 0.0,
                            #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                            # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                        })
                        line_ids.append(credit_line)
                        credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']

                    #if over_condition:
                    #get remaining value as USD for other currency (Eg. MMK)
                    #obj_bca_result should be input mmk ASCD_MMK amount
                    diff_cls_bca_adv = payslip_adv_cls_amount - obj_bca_result
                    #for other currency
                    other_currency_domain = [('currency_id', '!=', slip.employee_id.company_id.currency_id.id), ('partner_id', '=', slip.employee_id.user_id.partner_id.id), ('state', 'in', ['done', 'partial']), ('salary_advance', '=', True), ('request_date', '<=', slip.date_to), ('adv_exp_type', '=', 'advance')]
                    obj_other_currency_advs = self.env['employee.advance.expense'].sudo().search(other_currency_domain)
                    if not slip.input_line_ids.filtered(lambda r: r.code == "ASCD_MMK").amount:
                        obj_other_currency_advs = []
                    obj_oca_result = 0
                    for obj_oca in obj_other_currency_advs:
                        #gain loss calculation
                        #diff amount USD convert to MMK
                        # obj_oca_usd_amount = obj_oca.currency_id.with_context({'date': obj_oca.account_validate_date}).compute(slip.input_line_ids.filtered(lambda r: r.code == "ASCD_MMK").amount, slip.employee_id.company_id.currency_id)
                        obj_oca_usd_amount = obj_oca.currency_id._convert(
                            from_amount=slip.input_line_ids.filtered(lambda r: r.code == "ASCD_MMK").amount,
                            to_currency=slip.employee_id.company_id.currency_id,
                            company=self.env.company,
                            date=obj_oca.account_validate_date
                        )

                        gain_loss = diff_cls_bca_adv - obj_oca_usd_amount
                        #start advance integration
                        payslip_adv_cls_amount = slip.input_line_ids.filtered(lambda r: r.code == "ASCD_MMK").amount
                        if obj_oca.advance_expense_clearance_line_ids:
                            obj_oca_result += obj_oca.total_amount_expense - sum(result.total_amount for result in obj_oca.advance_expense_clearance_line_ids.search([('advance_id', '=', obj_oca.id)]))
                        else:
                            obj_oca_result += obj_oca.total_amount_expense
                        #remaining balance is greater than payslip cls amount
                        if obj_oca_result > payslip_adv_cls_amount:
                            #clearance done
                            if len(obj_base_currency_advs) == 1:
                                obj_oca_result = payslip_adv_cls_amount
                                adv_cls_list.append({'id': obj_oca, 'amount':obj_oca.total_amount_expense, 'amount_cls': obj_oca_result, 'description': line.salary_rule_id.name, 'state': 'partial'})
                            else:
                                #obj_oca_result = 100 ( Remaining to make clearance)
                                #total_amount_expense = 127
                                #payslip_adv_cls_amount = 10
                                #amount_cls = payslip_adv_cls_amount - (obj_oca_result - obj_oca.total_amount_expense)
                                #9999800 - (9999800.0 - 12770694.0)
                                amount_cls = payslip_adv_cls_amount - (obj_oca_result - obj_oca.total_amount_expense)
                                obj_oca_result = payslip_adv_cls_amount
                                if amount_cls == obj_oca.total_amount_expense:
                                    state = 'cleared'
                                else:
                                    state = 'partial'
                                adv_cls_list.append({'id': obj_oca, 'amount':obj_oca.total_amount_expense, 'amount_cls': payslip_adv_cls_amount, 'description': line.salary_rule_id.name, 'state': state})
                            #over_condition = False
                            # if not over_condition:
                            #     obj_oca_result -= obj_oca.total_amount_expense
                            #     adv_cls_list.append({'id':obj_oca,'amount_cls': payslip_adv_cls_amount})
                            #break
                        #full payment condition
                        elif obj_oca_result == payslip_adv_cls_amount:
                            over_condition = False
                            adv_cls_list.append({'id': obj_oca,'amount':obj_oca.total_amount_expense, 'amount_cls': obj_oca_result, 'description': line.salary_rule_id.name, 'state': 'cleared'})
                        #partial payment condition
                        else:
                            #store employee.advance.expense object
                            adv_cls_list.append({'id': obj_oca,'amount':obj_oca.total_amount_expense, 'amount_cls': obj_oca_result, 'description': line.salary_rule_id.name, 'state': 'cleared'})
                        #end advance integration
                        if debit_account_id:
                            debit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=False),
                                'account_id': debit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': obj_oca_usd_amount > 0.0 and obj_oca_usd_amount or 0.0,
                                'credit': obj_oca_usd_amount < 0.0 and -obj_oca_usd_amount or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(debit_line)

                            debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']

                        if credit_account_id:
                            credit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=True),
                                'account_id': credit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': diff_cls_bca_adv < 0.0 and -diff_cls_bca_adv or 0.0,
                                'credit': diff_cls_bca_adv > 0.0 and diff_cls_bca_adv or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(credit_line)

                            credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']

                        if gain_loss:
                            account_id = slip.contract_id.company_id.currency_exchange_journal_id.default_account_id.id
                            prec = self.env['decimal.precision'].precision_get('Account')
                            gain_loss_diff = (0, 0, {
                                'name': line.name,
                                'account_id': account_id,
                                'credit': 0.0 if float_compare(gain_loss, 0.0, precision_digits=prec) > 0 else -gain_loss,
                                'debit': gain_loss if float_compare(gain_loss, 0.0, precision_digits=prec) > 0 else 0.0,
                                'journal_id': slip.journal_id.id,
                                'partner_id': line._get_partner_id(credit_account=True),
                                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                                #'currency_id': company_currency != current_currency and current_currency.id or False,
                                #'amount_currency': company_currency != current_currency and diff_amount_currency or 0.0,
                            })
                            line_ids.append(gain_loss_diff)
                            if float_compare(gain_loss, 0.0, precision_digits=prec) > 0:
                                debit_sum += gain_loss_diff[2]['debit'] - gain_loss_diff[2]['credit']
                            else:
                                credit_sum += gain_loss_diff[2]['credit'] - gain_loss_diff[2]['debit']

                if line.salary_rule_id.settle_to_expense and line.amount != 0:
                    #payslip advance dedution amount
                    payslip_adv_cls_amount = line.amount * -1 if line.amount < 0 else line.amount

                    base_currency_domain = [('currency_id', '=', slip.employee_id.company_id.currency_id.id), ('partner_id', '=', slip.employee_id.user_id.partner_id.id), ('state', 'in', ['payable']), ('salary_advance', '=', True),('adv_exp_type', '=', 'expense')]# ('request_date', '<=', slip.date_to), 
                    obj_base_currency_advs = self.env['employee.advance.expense'].sudo().search(base_currency_domain)
                    if not slip.input_line_ids.filtered(lambda r: r.code == "RTST_USD").amount:
                        obj_base_currency_advs = []
                    #get base currency advance amount
                    obj_bca_result = 0
                    over_condition = False
                    for obj_bca in obj_base_currency_advs:
                        # if len(obj_base_currency_advs) == 1 and obj_bca.total_amount_expense != slip.input_line_ids.filtered(lambda r: r.code == "RTST_USD").amount:
                        #     raise UserError(_("Please fill total sum of reimbursement amount into RTST_USD inputs."))
                        # else:
                        obj_bca_result += obj_bca.total_amount_expense
                        adv_cls_list.append({'id': obj_bca, 'amount': obj_bca.total_amount_expense, 'state': 'cleared'})
                        if debit_account_id and obj_bca_result:
                            debit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=False),
                                'account_id': debit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': obj_bca.total_amount_expense > 0.0 and obj_bca.total_amount_expense or 0.0,
                                'credit': obj_bca.total_amount_expense < 0.0 and -obj_bca.total_amount_expense or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(debit_line)
                            debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']
                        if credit_account_id and obj_bca_result:
                            credit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=True),
                                'account_id': credit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': obj_bca.total_amount_expense < 0.0 and -obj_bca.total_amount_expense or 0.0,
                                'credit': obj_bca.total_amount_expense > 0.0 and obj_bca.total_amount_expense or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(credit_line)
                            credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']
                    if obj_base_currency_advs and round(obj_bca_result,2) != round(slip.input_line_ids.filtered(lambda r: r.code == "RTST_USD").amount,2):
                        raise UserError(_("Please fill total sum of reimbursement amount into RTST_USD inputs."))
                    #ForTestPurpose below comment
                    #obj_bca_result = 0

                    #deduct total resimbursement amount - usd total amount of reimbursement to get MMK reimbursement
                    diff_cls_bca_adv = payslip_adv_cls_amount - obj_bca_result
                    #for other currency
                    other_currency_domain = [('currency_id', '!=', slip.employee_id.company_id.currency_id.id), ('partner_id', '=', slip.employee_id.user_id.partner_id.id), ('state', 'in', ['payable']), ('salary_advance', '=', True), ('request_date', '<=', slip.date_to), ('adv_exp_type', '=', 'expense')]
                    obj_other_currency_advs = self.env['employee.advance.expense'].sudo().search(other_currency_domain)
                    if not slip.input_line_ids.filtered(lambda r: r.code == "RTST_MMK").amount:
                        obj_other_currency_advs = []
                    obj_oca_result = 0
                    for obj_oca in obj_other_currency_advs:
                        obj_oca_usd_amount = obj_oca.currency_id.with_context({'date': obj_oca.account_validate_date}).compute(obj_oca.total_amount_expense, slip.employee_id.company_id.currency_id)
                        # obj_oca_usd_amount_adv = obj_oca.currency_id.compute(obj_oca.total_amount_expense, slip.employee_id.company_id.currency_id)
                        obj_oca_usd_amount_adv = obj_oca.currency_id._convert(
                            from_amount=obj_oca.total_amount_expense,
                            to_currency=slip.employee_id.company_id.currency_id,
                            company=self.env.company,
                            date=obj_oca.account_validate_date
                        )
                        obj_oca_result += obj_oca.total_amount_expense
                        adv_cls_list.append({'id': obj_oca, 'amount': obj_oca.total_amount_expense, 'state': 'cleared'})

                        if debit_account_id:
                            debit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=False),
                                'account_id': debit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': obj_oca_usd_amount > 0.0 and obj_oca_usd_amount or 0.0,
                                'credit': obj_oca_usd_amount < 0.0 and -obj_oca_usd_amount or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(debit_line)

                            debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']

                        if credit_account_id:
                            credit_line = (0, 0, {
                                'name': line.name,
                                'partner_id': line._get_partner_id(credit_account=True),
                                'account_id': credit_account_id,
                                'journal_id': slip.journal_id.id,
                                'date': date,
                                'debit': obj_oca_usd_amount_adv < 0.0 and -obj_oca_usd_amount_adv or 0.0,
                                'credit': obj_oca_usd_amount_adv > 0.0 and obj_oca_usd_amount_adv or 0.0,
                                #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                                # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                            })
                            line_ids.append(credit_line)

                            credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']
                        gain_loss = obj_oca_usd_amount_adv - obj_oca_usd_amount
                        if gain_loss:
                            account_id = slip.contract_id.company_id.currency_exchange_journal_id.default_account_id.id
                            prec = self.env['decimal.precision'].precision_get('Account')
                            gain_loss_diff = (0, 0, {
                                'name': line.name,
                                'account_id': account_id,
                                'credit': 0.0 if float_compare(gain_loss, 0.0, precision_digits=prec) > 0 else -gain_loss,
                                'debit': gain_loss if float_compare(gain_loss, 0.0, precision_digits=prec) > 0 else 0.0,
                                'journal_id': slip.journal_id.id,
                                'partner_id': line._get_partner_id(credit_account=True),
                                #                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                                #'currency_id': company_currency != current_currency and current_currency.id or False,
                                #'amount_currency': company_currency != current_currency and diff_amount_currency or 0.0,
                            })
                            line_ids.append(gain_loss_diff)
                            if float_compare(gain_loss, 0.0, precision_digits=prec) > 0:
                                debit_sum += gain_loss_diff[2]['debit'] - gain_loss_diff[2]['credit']
                            else:
                                credit_sum += gain_loss_diff[2]['credit'] - gain_loss_diff[2]['debit']

                    if obj_other_currency_advs and obj_oca_result != slip.input_line_ids.filtered(lambda r: r.code == "RTST_MMK").amount:
                        raise UserError(_("Please fill total sum of reimbursement amount into RTST_MMK inputs."))
                        #end advance integration
                amount = currency.round(slip.credit_note and -line.total or line.total)
                if currency.is_zero(amount):
                    continue

                print("======================================")
                print(debit_sum)
                print("======================================")
                print("======================================")
                print(credit_sum)
                print("======================================")

                if debit_account_id and not line.salary_rule_id.clear_with_advance and not line.salary_rule_id.settle_to_expense:
                    debit_line = (0, 0, {
                        'name': line.name,
                        'partner_id': line._get_partner_id(credit_account=False),
                        'account_id': debit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amount > 0.0 and amount or 0.0,
                        'credit': amount < 0.0 and -amount or 0.0,
                        #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                        # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                    })
                    line_ids.append(debit_line)
                    debit_sum += debit_line[2]['debit'] - debit_line[2]['credit']

                if credit_account_id and not line.salary_rule_id.clear_with_advance and not line.salary_rule_id.settle_to_expense:
                    credit_line = (0, 0, {
                        'name': line.name,
                        'partner_id': line._get_partner_id(credit_account=True),
                        'account_id': credit_account_id,
                        'journal_id': slip.journal_id.id,
                        'date': date,
                        'debit': amount < 0.0 and -amount or 0.0,
                        'credit': amount > 0.0 and amount or 0.0,
                        #'analytic_account_id': line.salary_rule_id.analytic_account_id.id,
                        # 'tax_line_id': line.salary_rule_id.account_tax_id.id,
                    })
                    line_ids.append(credit_line)
                    credit_sum += credit_line[2]['credit'] - credit_line[2]['debit']
                print("======================================")
                print(debit_sum)
                print("======================================")
                print("======================================")
                print(credit_sum)
                print("======================================")
            if currency.compare_amounts(credit_sum, debit_sum) == -1:
                acc_id = slip.journal_id.default_account_id.id
                if not acc_id:
                    raise UserError(_('The Expense Journal "%s" has not properly configured the Credit Account!') % (slip.journal_id.name))
                adjust_credit = (0, 0, {
                    'name': _('Adjustment Entry'),
                    'partner_id': False,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': 0.0,
                    'credit': currency.round(debit_sum - credit_sum),
                })
                line_ids.append(adjust_credit)

            elif currency.compare_amounts(debit_sum, credit_sum) == -1:
                acc_id = slip.journal_id.default_account_id.id
                if not acc_id:
                    raise UserError(_('The Expense Journal "%s" has not properly configured the Debit Account!') % (slip.journal_id.name))
                adjust_debit = (0, 0, {
                    'name': _('Adjustment Entry'),
                    'partner_id': False,
                    'account_id': acc_id,
                    'journal_id': slip.journal_id.id,
                    'date': date,
                    'debit': currency.round(credit_sum - debit_sum),
                    'credit': 0.0,
                })
                line_ids.append(adjust_debit)
            move_dict['line_ids'] = line_ids

            
            move = self.env['account.move'].with_context(use_functional_rate=True).create(move_dict)
            slip.write({'move_id': move.id, 'date': date, 'state': 'done'})
            move.action_post()
            #integrate with employee advance expense and payslip
            settlement_ids = []
            for acl in adv_cls_list:
                if len(acl) == 3:
                    acl['id'].write({
                        'settlement_move_id': move.id,
                        'settlement_date': fields.Date.today(),
                        'settlement_account_by_id': self.env.user.id,
                        'state': acl['state'],

                        })
                    settlement_ids.append((0, 0, {
                        'label':acl['id'].name,
                        'amount': acl['amount'],
                        'type': 'advance' if acl['id'].adv_exp_type=='advance' else 'expense',
                        'note': acl['id'].x_studio_note,
                        'date': acl['id'].request_date,
                        'currency_id': acl['id'].currency_id.id,
                        }))
                else:
                    acl['id'].write({
                        'advance_expense_clearance_line_ids':
                            [(0, 0, {
                                'description': acl['description'],
                                'unit_amount': acl['amount_cls'],
                                'quantity': 1,
                                'cls_move_id': move.id,
                            })],
                        'state': acl['state'],

                        })
                    settlement_ids.append((0, 0, {
                        'label':acl['id'].name,
                        'amount': acl['amount'],
                        'type': 'advance' if acl['id'].adv_exp_type=='advance' else 'expense',
                        'note': acl['id'].x_studio_note,
                        'date': acl['id'].request_date,
                        'currency_id': acl['id'].currency_id.id,
                        }))
            slip.write({'settlement_ids':settlement_ids})


class HrPayslipLine(models.Model):
    _inherit = 'hr.payslip.line'

    def _get_partner_id(self, credit_account):
        """
        Get partner_id of slip line to use in account_move_line
        """
        # use partner of salary rule or fallback on employee's address
        # register_partner_id = self.salary_rule_id.register_id.partner_id
        # partner_id = register_partner_id.id or self.slip_id.employee_id.address_id.id
        # if credit_account:
        #     if register_partner_id or self.salary_rule_id.account_credit.internal_type in ('receivable', 'payable'):
        #         return partner_id
        # else:
        #     if register_partner_id or self.salary_rule_id.account_debit.internal_type in ('receivable', 'payable'):
        #         return partner_id
        # return False
        partner_id = self.slip_id.employee_id.address_id.id
        return partner_id


class HrPayslipInput(models.Model):
    _inherit = 'hr.payslip.input'

    input_type_id = fields.Many2one('hr.payslip.input.type', string='Type', required=False, domain="['|', ('id', 'in', _allowed_input_type_ids), ('struct_ids', '=', False)]")
    _allowed_input_type_ids = fields.Many2many('hr.payslip.input.type', related='payslip_id.struct_id.input_line_type_ids')
    code = fields.Char('Code',related='',readonly=False, required=True, help="The code that can be used in the salary rules")
    

class HrPayrollStructureType(models.Model):
    _inherit = 'hr.payroll.structure.type'
    _description = 'Salary Structure Type'

    struct_ids = fields.One2many('hr.payroll.structure', 'type_id', string="Structures")
    struct_ids_topay = fields.Many2many('hr.payroll.structure',string="Structures To Pay")
    
    def _compute_struct_type_count(self):
        for structure_type in self:
            structure_type.struct_type_count = len(structure_type.struct_ids_topay)


class HrPayslipSettlement(models.Model):
    _name = 'hr.payslip.settlement'
    _description = "Payslip Settlement"

    label = fields.Char(string='Number')
    amount = fields.Float(string='Requested Amount')
    date = fields.Date(string='Date')
    type = fields.Selection([('advance', 'Advance Request'), ('expense', 'Reimbursement Request')], string="Type")
    currency_id = fields.Many2one('res.currency', string='Currency', store=True)
    payslip_id = fields.Many2one('hr.payslip', string='Payslip')
    note = fields.Char(string="Note")


class HrLeaveType(models.Model):
    _inherit = 'hr.leave.type'

    validate_vacation = fields.Boolean(string="Apply Validation For Vacation (?)", default=False)
    leave_validation_type = fields.Selection([
        ('no_validation', 'No Validation'),
        ('hr', 'By Time Off Officer'),
        ('manager', "By Employee's Approver"),
        ('both', "Supervisor and Director")], default='both', string='Approval')

    def get_fiscal_date(self):
        fd = self.env.user.company_id.fiscalyear_last_day
        fm = self.env.user.company_id.fiscalyear_last_month
        now = datetime.now()
        e_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (now.year, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        )
        if now >= e_fiscal_date:
            e_fiscal_date = datetime.strptime(
                "%s-%s-%s" % (now.year + 1, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            ) + timedelta(days=1)
        s_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        ) + timedelta(days=1)
        return str(s_fiscal_date)

    def name_get(self):
        if not self._context.get('employee_id'):
            # leave counts is based on employee_id, would be inaccurate if not based on correct employee
            return super(HrLeaveType, self).name_get()
        res = []
        for record in self:
            name = record.name
            employee_id = self._get_contextual_employee_id()
            if record.requires_allocation == "yes" and not self._context.get('from_manager_leave_form'):
                name = "%(name)s (%(count)s)" % {
                    'name': name,
                    'count': _('%g remaining out of %g') % (
                        float_round(record.virtual_remaining_leaves, precision_digits=2) or 0.0,
                        float_round(record.max_leaves, precision_digits=2) or 0.0,
                    ) + (_(' hours') if record.request_unit == 'hour' else _(' days'))
                }
            elif employee_id and record.accumulated_leave:
                employee_id = self.env['hr.employee'].browse(employee_id)
                s_fiscal_date = self.get_fiscal_date()
                max_leaves = self.env['hr.leave'].search([('employee_id','=',employee_id.id),('holiday_status_id','=',record.id),('date_from','>',s_fiscal_date)]).mapped('leave_balance') or [employee_id.accumulated_leave]
                max_leaves = max(max_leaves) or 0
                name = "%(name)s (%(count)s)" % {
                    'name': name,
                    'count': _('%g remaining out of %g') % (
                        float_round(employee_id.accumulated_leave, precision_digits=2) or 0.0,
                        float_round(max_leaves, precision_digits=2) or 0.0,
                    ) + (_(' hours') if record.request_unit == 'hour' else _(' days'))
                }
            elif employee_id and record.unpaid_accumulated_leave:
                employee_id = self.env['hr.employee'].browse(employee_id)
                s_fiscal_date = self.get_fiscal_date()
                max_leaves = self.env['hr.leave'].search([('employee_id','=',employee_id.id),('holiday_status_id','=',record.id),('date_from','>',s_fiscal_date)]).mapped('leave_balance') or [employee_id.unpaid_accumulated_leave]
                max_leaves = max(max_leaves) or 0
                name = "%(name)s (%(count)s)" % {
                    'name': name,
                    'count': _('%g remaining out of %g') % (
                        float_round(employee_id.unpaid_accumulated_leave, precision_digits=2) or 0.0,
                        float_round(max_leaves, precision_digits=2) or 0.0,
                    ) + (_(' hours') if record.request_unit == 'hour' else _(' days'))
                }
            res.append((record.id, name))
        return res

class HrLeave(models.Model):
    _inherit = 'hr.leave'

    #@api.constrains('holiday_status_id', 'request_date_from')
    #def _check_vacation_request_late(self):
    #    if self.holiday_status_id.validate_vacation == True and self.request_date_from < fields.Date.today() and self.env.user.has_group('isy_custom.leave_validation') == False:
    #        raise ValidationError(_("Vacation Leave is not allowed to create backdate!"))

    def _get_overlapping_contracts(self, contract_states=None):
        self.ensure_one()
        if contract_states is None:
            contract_states = [
                '|',
                ('state', 'not in', ['draft', 'cancel']),
                '&',
                ('state', '=', 'draft'),
                ('kanban_state', '=', 'done')
            ]
        domain = AND([contract_states, [
            ('employee_id', '=', self.employee_id.id),
            ('company_id','=',self.env.user.company_id.id),
            ('date_start', '<=', self.date_to),
            '|',
                ('date_end', '>=', self.date_from),
                '&',
                    ('date_end', '=', False),
                    ('state', '!=', 'close')
        ]])
        return self.env['hr.contract'].sudo().search(domain)


class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    """
    @api.model_create_multi
    def create(self, vals_list):
        # OVERRIDE
        ACCOUNTING_FIELDS = ('debit', 'credit', 'amount_currency')
        BUSINESS_FIELDS = ('price_unit', 'quantity', 'discount', 'tax_ids')
        # check amount_currency
        for vals in vals_list:
            move = self.env['account.move'].browse(vals['move_id'])
            vals.setdefault('company_currency_id', move.company_id.currency_id.id) # important to bypass the ORM limitation where monetary fields are not rounded; more info in the commit message

            if move.is_invoice(include_receipts=True):
                currency = move.currency_id
                partner = self.env['res.partner'].browse(vals.get('partner_id'))
                taxes = self.resolve_2many_commands('tax_ids', vals.get('tax_ids', []), fields=['id'])
                tax_ids = set(tax['id'] for tax in taxes)
                taxes = self.env['account.tax'].browse(tax_ids)

                # Ensure consistency between accounting & business fields.
                # As we can't express such synchronization as computed fields without cycling, we need to do it both
                # in onchange and in create/write. So, if something changed in accounting [resp. business] fields,
                # business [resp. accounting] fields are recomputed.
                if any(vals.get(field) for field in ACCOUNTING_FIELDS):
                    if vals.get('currency_id'):
                        balance = vals.get('amount_currency', 0.0)
                    else:
                        balance = vals.get('debit', 0.0) - vals.get('credit', 0.0)
                    price_subtotal = self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.type,
                    ).get('price_subtotal', 0.0)
                    vals.update(self._get_fields_onchange_balance_model(
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        balance,
                        move.type,
                        currency,
                        taxes,
                        price_subtotal
                    ))
                    vals.update(self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.type,
                    ))
                elif any(vals.get(field) for field in BUSINESS_FIELDS):
                    vals.update(self._get_price_total_and_subtotal_model(
                        vals.get('price_unit', 0.0),
                        vals.get('quantity', 0.0),
                        vals.get('discount', 0.0),
                        currency,
                        self.env['product.product'].browse(vals.get('product_id')),
                        partner,
                        taxes,
                        move.type,
                    ))
                    vals.update(self._get_fields_onchange_subtotal_model(
                        vals['price_subtotal'],
                        move.type,
                        currency,
                        move.company_id,
                        move.date,
                    ))

        lines = super(AccountMoveLine, self).create(vals_list)

        moves = lines.mapped('move_id')
        if self._context.get('check_move_validity', True):
            moves._check_balanced()
        moves._check_fiscalyear_lock_date()
        lines._check_tax_lock_date()

        return lines
    """

    def get_balance(self):
        account_ids = self.env['account.account'].search(['&','|','&',('account_type','=',9), ('x_community_deposit','=',True),('code','=','251015'),('company_id','=',4)])
        aml_datas = self.search_read([
            ('account_id','in',account_ids.ids),
            ('move_id.state','=','posted'),
            ('date','<=',date.today())
            ],['account_id','debit','credit'])
        
        fp = io.BytesIO()
        workbook = xlsxwriter.Workbook(fp, {})
        worksheet = workbook.add_worksheet('Community Deposit Balance')

        header = workbook.add_format({'font_size': 10, 'border': 1, 'align': 'center', 'bold':True,
                                      'valign': 'vcenter', 'bg_color': 'silver'})
        format_cell_qty = workbook.add_format({'font_size': 10, 'border': 1, 'align': 'right','num_format':'_(* #,##0.00_);_(* \(#,##0.00\);_(* "-"??_);_(@_)', 'bold': True, 'font_color':'#666666' })
        format_cell = workbook.add_format({'font_size': 10, 'border': 1, 'align': 'left','indent':1, 'bold':True, 'font_color':'#666666' })
        #header_lst = ['Date','ERP Count','ERP Balance','ERP INT Count','ERP INT Balance','Mifo Count','Mifo Balance','Mifo INT Count','Mifo INT Balance']
        #worksheet.write_row('A1',header_lst,header)
        row = 0
        col = 0
        worksheet.write(row,col,'Account Name',header)
        worksheet.set_column(col,col,40)
        col += 1
        worksheet.write(row,col,'Debit',header)
        worksheet.set_column(col,col+2,15)
        col += 1
        worksheet.write(row,col,'Credit',header)
        col += 1
        worksheet.write(row,col,'Balance',header)
        
        row += 1
        for acc_id in account_ids:
            res = list(filter(lambda x: x.get('account_id')[0]==acc_id.id,aml_datas))
            debit = sum([x.get('debit') for x in res])
            credit = sum([x.get('credit') for x in res])
            balance = debit-credit
            col = 0
            worksheet.write(row,col,acc_id.display_name,format_cell)
            col += 1
            worksheet.write(row,col,debit,format_cell_qty)
            col += 1
            worksheet.write(row,col,credit,format_cell_qty)
            col += 1
            worksheet.write(row,col,balance,format_cell_qty)
            col += 1
            row += 1
        workbook.close()
        fp.seek(0)
        file = base64.encodestring(fp.read())
        fp.close()

        current_str = str(date.today())
        data_id = self.env['ir.attachment'].create({
                        'name': "Community Deposit Balance on " + current_str + ".xlsx",
                        'type': 'binary',
                        'datas': file,
                        # 'datas_fname': 'Community Deposit Balance on ' + ' ' + current_str + '.xlsx',
                        'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    })
        return [(6,0, [data_id.id])]


    def _cron_sending_scholarship_fund_noti(self):
        _logger.debug('###### Ohnmar # Sending email for Schedular Fund.')
        template = self.env.ref('mt_isy.scholarship_acc_for_eom_mail_template')
        template.attachment_ids = self.get_balance()
        self.env['mail.template'].browse(template.id).send_mail(self.search([],limit=1).id)

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    res_currency_rate_functional_details = fields.One2many('res.currency.rate.functional','currency_id', string="Functional Currency Details")
    functional_rate = fields.Float(compute='_compute_current_functional_rate', string='Functional Rate', digits=(12, 6),
                        help='The rate of the currency to the currency of rate 1.')


    @api.model
    def _get_conversion_functional_rate(self, from_currency, to_currency, company, date):
        currency_rates = (from_currency + to_currency)._get_functional_rates(company, date)
        res = currency_rates.get(to_currency.id) / currency_rates.get(from_currency.id)
        return res

    def _convert(self, from_amount, to_currency, company, date, round=True):
        """Returns the converted amount of ``from_amount``` from the currency
           ``self`` to the currency ``to_currency`` for the given ``date`` and
           company.

           :param company: The company from which we retrieve the convertion rate
           :param date: The nearest date from which we retriev the conversion rate.
           :param round: Round the result or not
        """
        self, to_currency = self or to_currency, to_currency or self
        assert self, "convert amount from unknown currency"
        assert to_currency, "convert amount to unknown currency"
        assert company, "convert amount from unknown company"
        assert date, "convert amount from unknown date"
        # apply conversion rate
        if self == to_currency:
            to_amount = from_amount
        elif self._context.get('use_functional_rate') and self._context.get('use_functional_rate') != False:
            to_amount = from_amount * self._get_conversion_functional_rate(self, to_currency, company, date)
        else:
            to_amount = from_amount * self._get_conversion_rate(self, to_currency, company, date)
        # apply rounding
        return to_currency.round(to_amount) if round else to_amount

    def _get_functional_rates(self, company, date):
        query = """SELECT c.id,
                          COALESCE((SELECT r.currency_rate FROM res_currency_rate_functional r
                                  WHERE r.currency_id = c.id AND r.name <= %s
                                    AND (r.company_id IS NULL OR r.company_id = %s)
                               ORDER BY r.company_id, r.name DESC
                                  LIMIT 1), 1.0) AS rate
                   FROM res_currency c
                   WHERE c.id IN %s"""
        self._cr.execute(query, (date, company.id, tuple(self.ids)))
        currency_rates = dict(self._cr.fetchall())
        return currency_rates

    @api.depends('res_currency_rate_functional_details.currency_rate')
    def _compute_current_functional_rate(self):
        date = self._context.get('date') or fields.Date.today()
        company = self.env['res.company'].browse(self._context.get('company_id')) or self.env.company
        # the subquery selects the last rate before 'date' for the given currency/company
        currency_rates = self._get_functional_rates(company, date)
        for currency in self:
            currency.functional_rate = currency_rates.get(currency.id) or 1.0

class ResCurrencyRateFunctional(models.Model):
    _name = 'res.currency.rate.functional'
    #functional_rate = payslip.currency_id.search([('name','=','MMK')]).functional_rate <<<<< Use in payslip
    name = fields.Date(string="Date", default=fields.Datetime.now().date())
    currency_rate = fields.Float(string="Currency Rate")
    company_id = fields.Many2one('res.company', string="Company", default=lambda self: self.env.user.company_id)
    currency_id = fields.Many2one('res.currency')



class HrPayslipApproval(models.Model):
    _name = 'hr.payslip.approval'
    _inherit = ['mail.thread']

    name = fields.Char(string="Reference Number", readonly=True,
                       required=True, copy=False, default='New')
    request_employee_id = fields.Many2one("hr.employee", string="Request By")
    date_from = fields.Date(string="Request Date From")
    date_to = fields.Date(string="Request Date To")
    first_approval = fields.Many2one('hr.employee', string="First Approval Person")
    second_approval = fields.Many2one('hr.employee', string="Second Approval Person")
    hr_payslip_approval_details = fields.One2many('hr.payslip.approval.details', 'hr_payslip_approval_id', string="Details")
    expatriate_total = fields.Float(
        string="Total Monthly Salary For Expat(40%)", compute="_compute_total", readonly=True)
    expatriate_total_60 = fields.Float(
        string="Total Monthly Salary For Expat(60%)", compute="_compute_total", readonly=True)
    local_total = fields.Float(
        string="Total Monthly Salary For Local", compute="_compute_total", readonly=True)
    expatriate_retirement_total = fields.Float(
        string=" Total Monthly Retirement for Expat(40%)", compute="_compute_retirement_total", readonly=True)
    expatriate_retirement_total_60 = fields.Float(
        string=" Total Monthly Retirement for Expat(60%)", compute="_compute_retirement_total", readonly=True)
    local_retirement_total = fields.Float(
        string=" Total Monthly Retirement for Local", compute="_compute_retirement_total", readonly=True)
    total_extra_duty_allowance = fields.Float(
        string="Total Monthly Extra Duty Allowance for Expat(40%)", compute="_compute_extra_duty_total", readonly=True)
    total_extra_duty_allowance_60 = fields.Float(
        string="Total Monthly Extra Duty Allowance for Expat(60%)", compute="_compute_extra_duty_total", readonly=True)
    all_total = fields.Float(
        string="Total", compute="_compute_all_total", readonly=True)
    all_total_tmp = fields.Float(
        string="Temp", compute="_compute_all_total", readonly=True)
    state = fields.Selection([('draft','Draft'), ('waitingforfirstapproval','WaitingForApproval'),('waitingforsecondapproval','WaitingForSecondApproval'),('done','Done'),('cancelled','Cancelled')], string="State", default='draft',track_visibility='onchange')
    amount_for_expat = fields.Float(
        string="Total Amount for Expat(40%)", compute="_compute_all_total", readonly=True)
    amount_for_expat_60 = fields.Float(
        string="Total Amount for Expat(60%)", compute="_compute_all_total", readonly=True)
    amount_for_local = fields.Float(
        string="Total Amount for Local", compute="_compute_all_total", readonly=True)
    datas = fields.Binary()

    @api.depends('hr_payslip_approval_details.employee_type', 'hr_payslip_approval_details.monthly_salary')
    def _compute_total(self):
        for rec in self:
            local_total =0
            expatriate_total_60 = 0
            expatriate_total = 0
            for obj in rec.hr_payslip_approval_details:
                if obj.employee_type == 'local':
                    local_total += obj.monthly_salary
                else:
                    if obj.contract_type == 'expat60':
                        expatriate_total_60 += obj.monthly_salary
                    else:
                        expatriate_total += obj.monthly_salary
            rec.local_total = local_total
            rec.expatriate_total = expatriate_total
            rec.expatriate_total_60 = expatriate_total_60

    @api.depends('hr_payslip_approval_details.employee_type', 'hr_payslip_approval_details.monthly_retirement')
    def _compute_retirement_total(self):
        for rec in self:
            expatriate_retirement_total_60 = 0
            expatriate_retirement_total = 0
            local_retirement_total = 0
            for obj in rec.hr_payslip_approval_details:
                if obj.employee_type == 'expatriate':
                    if obj.contract_type == 'expat60':
                        expatriate_retirement_total_60 += obj.monthly_retirement
                    else:
                        expatriate_retirement_total += obj.monthly_retirement
                else:
                    local_retirement_total += obj.monthly_retirement
            rec.expatriate_retirement_total_60 = expatriate_retirement_total_60
            rec.expatriate_retirement_total = expatriate_retirement_total
            rec.local_retirement_total = local_retirement_total

    @api.depends('hr_payslip_approval_details.employee_type', 'hr_payslip_approval_details.monthly_extra_duty_amount')
    def _compute_extra_duty_total(self):
        for rec in self:
            total_extra_duty_allowance_60 = 0
            total_extra_duty_allowance = 0
            for obj in rec.hr_payslip_approval_details:
                if obj.employee_type == 'expatriate':
                    if obj.contract_type == 'expat60':
                        total_extra_duty_allowance_60 += obj.monthly_extra_duty_amount
                    else:
                        total_extra_duty_allowance += obj.monthly_extra_duty_amount
            rec.total_extra_duty_allowance_60 = total_extra_duty_allowance_60
            rec.total_extra_duty_allowance = total_extra_duty_allowance

    @api.depends('local_total', 'expatriate_total','expatriate_total_60', 'expatriate_retirement_total','expatriate_retirement_total_60', 'local_retirement_total', 'total_extra_duty_allowance','total_extra_duty_allowance_60')
    def _compute_all_total(self):
        for rec in self:
            rec.amount_for_expat = rec.expatriate_total + rec.expatriate_retirement_total + rec.total_extra_duty_allowance
            rec.amount_for_expat_60 = rec.expatriate_total_60 + rec.expatriate_retirement_total_60 + rec.total_extra_duty_allowance_60
            rec.amount_for_local = rec.local_total + rec.local_retirement_total
            # rec.all_total = rec.local_total + rec.expatriate_total + rec.expatriate_retirement_total + rec.local_retirement_total + rec.total_extra_duty_allowance
            rec.all_total = rec.amount_for_expat + rec.amount_for_expat_60 + rec.amount_for_local
            rec.all_total_tmp = 0
            
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.hr.payslip.approval') or 'New'
        result = super(HrPayslipApproval, self).create(vals)
        return result

    def cancel_approve(self):
        self.state= 'cancelled'
    
    def request_for_first_approval(self):
        self.state = 'waitingforfirstapproval'

    def request_for_second_approval(self):
        if self.env.user.id == self.first_approval.user_id.id:
            self.state = 'done'
        else:
            raise ValidationError(
                _("You are not allowed to approve this!"))
    
    def second_approved(self):
        if self.env.user.id == self.second_approval.user_id.id:
            self.state = 'done'
        else:
            raise ValidationError(
                _("You are not allowed to approve this!"))

    def print_to_excel(self):
        fp = io.BytesIO()
        workbook = xlsxwriter.Workbook(fp, {})
        
        header = workbook.add_format({'font_size': 11, 'text_wrap':True, 'bold': True, 'border': 0, 'align': 'center',
                                      'valign': 'vcenter'})
        format_cell_qty = workbook.add_format({'font_size': 10, 'border': 0, 'align': 'right','num_format':'#,##0.00','valign': 'vcenter'})
        format_cell = workbook.add_format({'font_size': 10, 'border': 0, 'text_wrap':True, 'align': 'left','valign': 'vcenter'})
        format_cell_center = workbook.add_format({'font_size': 10, 'border': 0, 'text_wrap':True, 'align': 'center','valign': 'vcenter'})
        format_cell_title = workbook.add_format({'font_size': 10, 'border': 0, 'text_wrap':True, 'align': 'left','bold':True,'valign': 'vcenter'})
        format_cell_link = workbook.add_format({'font_size': 10, 'border': 0, 'align': 'left', 'font_color':'#008784'})
        for rec in self:
            worksheet = workbook.add_worksheet(rec.name)
            row = 0
            col=8
            worksheet.write(row,col,'State',format_cell)
            col+=1
            worksheet.write(row,col,dict(rec._fields['state'].selection).get(rec.state),format_cell)
            worksheet.set_row(row,10)
            row+=1
            col = 1
            worksheet.merge_range(row,col,row,col+8,rec.name,header)
            col+=7
            worksheet.set_row(row,24)
            row+=1
            col=1
            worksheet.write(row,col,'Request Date From',format_cell)
            col+=1
            worksheet.write(row,col,str(rec.date_from),format_cell)
            row+=1
            col=1
            worksheet.write(row,col,'Request Date To',format_cell)
            col+=1
            worksheet.write(row,col,str(rec.date_to),format_cell)
            row+=1
            col=1
            worksheet.write(row,col,rec.request_employee_id.name,format_cell_link)
            row+=1
            col=1
            worksheet.write(row,col,rec.first_approval.name,format_cell_link)
            row+=1
            col=1
            worksheet.write(row,col,'Total',format_cell)
            col+=1
            worksheet.write(row,col,rec.all_total,format_cell_qty)

            row+=1
            col=1
            worksheet.write(row,col,'Total Monthly Salary For Expat(40%)',format_cell)
            worksheet.set_column(col,col,22)
            col+=1
            worksheet.write(row,col,rec.expatriate_total,format_cell_qty)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Total Monthly Salary For Expat(60%)',format_cell)
            worksheet.set_column(col,col,22)
            col+=1
            worksheet.write(row,col,rec.expatriate_total_60,format_cell_qty)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Total Monthly Salary For Local',format_cell)
            worksheet.set_column(col,col,22)
            col+=1
            worksheet.write(row,col,rec.local_total,format_cell_qty)
            worksheet.set_column(col,col,10)
            worksheet.set_row(row,24)

            row+=1
            col=1
            worksheet.write(row,col,'Total Monthly Retirement for Expat(40%)',format_cell)
            col+=1
            worksheet.write(row,col,rec.expatriate_retirement_total,format_cell_qty)
            col+=1
            worksheet.write(row,col,'Total Monthly Retirement for Expat(60%)',format_cell)
            col+=1
            worksheet.write(row,col,rec.expatriate_retirement_total_60,format_cell_qty)
            col+=1
            worksheet.write(row,col,'Total Monthly Retirement for Local',format_cell)
            col+=1
            worksheet.write(row,col,rec.local_retirement_total,format_cell_qty)
            worksheet.set_row(row,24)
            row+=1
            col=1
            worksheet.write(row,col,'Total Monthly Extra Duty Allowance for Expat(40%)',format_cell)
            col+=1
            worksheet.write(row,col,rec.total_extra_duty_allowance,format_cell_qty)
            col+=1
            worksheet.write(row,col,'Total Monthly Extra Duty Allowance for Expat(60%)',format_cell)
            col+=1
            worksheet.write(row,col,rec.total_extra_duty_allowance_60,format_cell_qty)
            col+=1
            worksheet.set_row(row,24)
            
            if rec.x_note:
                row+=1
                col=1
                worksheet.write(row,col,rec.x_note,format_cell)
            worksheet.set_row(row+1,10)
            row+=2
            col=0
            worksheet.set_column(col,col,4)
            worksheet.write(row,col,'#',header)
            col+=1
            worksheet.write(row,col,'Employee',format_cell_title)
            col+=1
            worksheet.write(row,col,'Department',format_cell_title)
            worksheet.set_column(col,col,13)
            col+=1
            worksheet.write(row,col,'Job Title',format_cell_title)
            col+=1
            worksheet.write(row,col,'Employee Type',format_cell_title)
            col+=1
            worksheet.write(row,col,'Contract Type',format_cell_title)
            col+=1
            worksheet.write(row,col,'Wage',format_cell_title)
            col+=1
            worksheet.write(row,col,'Monthly Salary',format_cell_title)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Annual Retirement',format_cell_title)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Monthly Retirement',format_cell_title)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Extra Duty Allowance (%)',format_cell_title)
            worksheet.set_column(col,col,10)
            col+=1
            worksheet.write(row,col,'Extra Duty Allowance Amount',format_cell_title)
            worksheet.set_column(col,col,10)
            worksheet.set_row(row,30)
            number=0
            for line in rec.hr_payslip_approval_details.sorted(lambda x:x.name.name):
                row+=1
                col=0
                number+=1
                worksheet.write(row,col,number,format_cell_center)
                col+=1
                worksheet.write(row,col,line.name.name,format_cell)
                col+=1
                worksheet.write(row,col,line.name.x_department or '',format_cell)
                col+=1
                worksheet.write(row,col,line.job_title or '',format_cell)
                col+=1
                worksheet.write(row,col,dict(rec.hr_payslip_approval_details._fields['employee_type'].selection).get(line.employee_type),format_cell)
                col+=1
                worksheet.write(row,col,dict(line._fields['contract_type'].selection).get(line.contract_type),format_cell)
                col+=1
                worksheet.write(row,col,line.wage,format_cell_qty)
                col+=1
                worksheet.write(row,col,line.monthly_salary,format_cell_qty)
                col+=1
                worksheet.write(row,col,line.annual_retirement,format_cell_qty)
                col+=1
                worksheet.write(row,col,line.monthly_retirement,format_cell_qty)
                col+=1
                worksheet.write(row,col,line.extra_duty_percent,format_cell_qty)
                col+=1
                worksheet.write(row,col,line.monthly_extra_duty_amount,format_cell_qty)

        workbook.close()
        fp.seek(0)
        file = base64.encodestring(fp.read())
        self.write({'datas': file})
        filename = 'Payslip Approval %s'%(datetime.now())
        return {
                'type' : 'ir.actions.act_url',
                'url':   '/web/binary/download_document?model=%s&field=datas&id=%s&filename=%s.xlsx'%(self[0]._name, self[0].id,filename),
                'target': 'self',
                }


class HrPayslipApprovalDetails(models.Model):
    _name = 'hr.payslip.approval.details'

    hr_payslip_approval_id = fields.Many2one(
        "hr.payslip.approval", ondelete='cascade')
    name = fields.Many2one('hr.employee', string="Employee")
    employee_type = fields.Selection([('local','Local'),('expatriate','Expatriate')], string="Employee Type")
    job_title = fields.Char(string="Job Title")
    wage = fields.Float(string="Wage")
    monthly_salary = fields.Float(string="Monthly Salary")
    annual_retirement = fields.Float(string="Annual Retirement")
    monthly_retirement = fields.Float(string="Monthly Retirement")
    extra_duty_percent = fields.Float(string="Extra Duty Allowance(%)", default=0)
    monthly_extra_duty_amount = fields.Float(string="Extra Duty Allowance Amount", compute="_get_monthly_extra_duty")
    contract_type = fields.Selection([('local100','Local'),('expat60','60%'),('expat40','40%')],string='Contract Type')

    @api.depends('extra_duty_percent', 'monthly_salary')
    def _get_monthly_extra_duty(self):
        for rec in self:
            monthly_extra_duty_amount = 0
            if rec.extra_duty_percent:
                monthly_extra_duty_amount = ( rec.monthly_salary * \
                    (rec.extra_duty_percent/100) )
            rec.monthly_extra_duty_amount += monthly_extra_duty_amount * 8.333/100

class HrPayslipProcessRequest(models.Model):
    _name = 'hr.payslip.process.request'
    _inherit = ['mail.thread']

    def _get_default_employee(self):
        obj_employee = self.env['hr.employee'].sudo().search([('user_id','=',self.env.user.id)])
        return obj_employee.id

    def _get_default_approval_person(self):
        approval_id = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.hr_payslip_process_request_approval_id', 0)
        return int(approval_id)

    @api.depends('deduction_details')
    def _get_total_school_trip_adjustment(self):
        for rec in self:
            total_school_trip_adjustment =0
            for recdd in rec.deduction_details:
                if recdd.deduction_type == 'school_trip':
                    total_school_trip_adjustment += recdd.amount
            rec.total_school_trip_adjustment = total_school_trip_adjustment

    @api.depends('deduction_details')
    def _get_total_tuition_fee_adjustment(self):
        for rec in self:
            total_tuition_fee_adjustment=0
            for recdd in rec.deduction_details:
                if recdd.deduction_type == 'tuition_fee':
                    total_tuition_fee_adjustment += recdd.amount
            rec.total_tuition_fee_adjustment = total_tuition_fee_adjustment
    
    @api.depends('deduction_details')
    def _get_total_other_adjustment(self):
        for rec in self:
            total_other_adjustment=0
            for recdd in rec.deduction_details:
                if recdd.deduction_type == 'other':
                    total_other_adjustment += recdd.amount
            rec.total_other_adjustment = total_other_adjustment

    @api.depends('cash_allocation_requests','deduction_details')
    def compute_total(self):
        for rec in self:
            total_car = sum(rec.cash_allocation_requests.mapped('amount'))
            if rec.is_expat == False:
                net_salary = rec.monthly_salary - total_car - rec.total_school_trip_adjustment - rec.total_tuition_fee_adjustment - rec.total_other_adjustment
                eom_date = rec.requested_date.date()
                if eom_date.day > 10: # 10th is local staff last day to request
                    eom_date = eom_date.replace(day=28)+timedelta(days=4)
                    eom_date = eom_date - timedelta(days=eom_date.day)
                accumulated_savings = self.env['account.move.line'].sudo().search([('account_id.savings_for_education','=',True),('partner_id','=',rec.request_employee_id.sudo().address_id.id),('date','<=',eom_date),('move_id.state','=','posted')])
                # Saving is Credit nature
                total_car += sum(accumulated_savings.mapped('credit'))-sum(accumulated_savings.mapped('debit'))
                rec.total_car = total_car
                rec.net_salary = net_salary
            else:
                rec.total_car = total_car
                rec.net_salary = rec.total_salary


    name = fields.Char(string="Reference Number", readonly=True,
                       required=True, copy=False, default='New')
    request_employee_id = fields.Many2one(
        "hr.employee", string="Request By", default=_get_default_employee)
    approval_person = fields.Many2one(
        'hr.employee', string="Approval Person", default=_get_default_approval_person)
    monthly_salary = fields.Float(string="Total Monthly Salary")
    retirement_salary = fields.Float(string="Total Retirement")

    monthly_salary_gty = fields.Float(string='GTY Salary (40%)')
    monthly_salary_isya = fields.Float(string='ISYA Salary (60%)')
    retirement_salary_gty = fields.Float(string="GTY Retirement (40%)")
    retirement_salary_isya = fields.Float(string="ISYA Retirement (60%)")

    total_salary = fields.Float(string="Total Salary")
    total_car = fields.Float("Total Allocation Requests",compute="compute_total",store=True)
    net_salary = fields.Float("Net Salary",compute="compute_total",store=True)
    total_school_trip_adjustment = fields.Float(string="School Trip Adjustment Total", compute=_get_total_school_trip_adjustment)
    total_tuition_fee_adjustment = fields.Float(string="Tuition Fee Adjustment Total", compute=_get_total_tuition_fee_adjustment)
    total_other_adjustment = fields.Float(string="Other Adjustment Total", compute=_get_total_other_adjustment)
    state = fields.Selection([('draft', 'Draft'), ('waitingforapproval', 'WaitingForApproval'), ('done', 'Done'), ('cancelled', 'Cancelled')], string="State", default='draft', track_visibility='onchange')
    cash_allocation_requests = fields.One2many('hr.payslip.cash.allocation.requests', 'hr_payslip_process_request_id', string="Cash Allocation Requests")
    deduction_details = fields.One2many(
        'hr.payslip.deduction.details', 'hr_payslip_deduction_request_id', string="Deduction Details")
    bank_details = fields.One2many('hr.payslip.bank.details', 'hr_payslip_bank_request_id', string="Bank Details")
    note = fields.Text(string="Note")
    is_after_lastday = fields.Boolean('Request after Last Day?')
    msg_validation = fields.Char(string="Warning")
    requested_date = fields.Datetime('Requested Date', default=lambda s: fields.Datetime.now())
    is_expat = fields.Boolean('Is Expat?',compute="compute_is_expat")
    is_donation = fields.Boolean('Donation',compute="compute_is_donation",store=True)
    allowance_utility = fields.Float('Utility Allowance')

    @api.depends('cash_allocation_requests')
    def compute_is_donation(self):
        for rec in self:
            is_donation = False
            for car in rec.cash_allocation_requests:
                if (car.amount!=0 and car.name in ('donation_uws','donation_yas','donation_clc','donation_chinthe')):
                    is_donation = True
            rec.is_donation = is_donation

    def get_donation_list(self):
        donation_uws = self.cash_allocation_requests.filtered(lambda x: x.name=='donation_uws').amount
        donation_yas = self.cash_allocation_requests.filtered(lambda x: x.name=='donation_yas').amount
        donation_clc = self.cash_allocation_requests.filtered(lambda x: x.name=='donation_clc').amount
        donation_chinthe = self.cash_allocation_requests.filtered(lambda x: x.name=='donation_chinthe').amount
        #return (donation_uws,donation_yas,donation_clc,donation_chinthe)
        return (donation_chinthe,0)

    @api.depends('request_employee_id')
    def compute_is_expat(self):
        for rec in self:
            is_expat = False if 'Local' in [
                x.name for x in rec.request_employee_id.sudo().category_ids.sudo()] else True
            rec.is_expat = is_expat

    def cancel_approve(self):
        #comment below validation because there has no more needed for cancel action when the state is done.
        #when state is done, it can able to reset draft.
        #cancel is the process end.
        # if self.state == 'done' and not self.env.user.has_group('hr_payroll.group_hr_payroll_manager'):
        #     raise ValidationError(_("Please ask Business Manager to cancel your record as your request is already approved.\n Cancellation after approved will be effect only for adjustment details and it cannot reverse for cash allocation request as it is already update in your cash allocation information.\n You can create new requests and fill cash allocation again or adjustment details or both. \n Then, it will update your cash allocation again."))
        for rec in self:
            rec.is_after_lastday = False
            rec.msg_validation = False
            rec.state = 'cancelled'
    
    def check_allocation_request(self):
        for rec in self:

            # total_allocation_request_gty = sum(rec.cash_allocation_requests.filtered(lambda x: x.name not in ('401_k','overseas_bank')).mapped('amount'))
            # total_allocation_request_isya = sum(rec.cash_allocation_requests.filtered(lambda x: x.name in ('401_k','overseas_bank')).mapped('amount'))
            total_allocation_request_isya = sum(rec.cash_allocation_requests.mapped('amount'))
            total_deduction_request = sum(rec.deduction_details.mapped('amount'))
            # if (rec.monthly_salary_gty+rec.retirement_salary_gty) < total_allocation_request_gty:
            #     raise UserError("Your combined allocations (1+2+3+4) cannot be more than your GTY salary (40%).")
            expat_salary = float_round(rec.monthly_salary_isya,2)+float_round(rec.retirement_salary_isya,2)
            if expat_salary < float_round(rec.monthly_salary_isya+rec.retirement_salary_isya,2):
                expat_salary = float_round(rec.monthly_salary_isya+rec.retirement_salary_isya,2)
            if rec.is_expat and (expat_salary+rec.allowance_utility) < (total_allocation_request_isya+total_deduction_request):
                raise UserError("Your allocations and deductions cannot be more than your ISYA salary (60%).")
            elif not rec.is_expat and (rec.monthly_salary_gty) < (total_allocation_request_isya+total_deduction_request):
                raise UserError("Your allocations and deductions cannot be more than your monthly salary.")


            # if monthly_salary < (total_allocation_request+total_deduction_request):
            #     raise UserError("Your allocation (deduction) is more than your salary (60%) so please contact slinn@isyedu.org.")

    # def get_contract(self):
    #     for rec in self:
    #         if 'Local' not in rec.request_employee_id.sudo().category_ids.sudo().mapped('name'): # Expat - ISYA 
    #             obj_contract_isya = rec.env['hr.contract'].sudo().search(
    #                 [('company_id.parent_id','=',False),('employee_id', '=', rec.request_employee_id.id), ('state', 'in', ['open', 'pending'])])
    #             obj_contract_gty = rec.env['hr.contract'].sudo().search(
    #                 [('company_id.parent_id','!=',False),('employee_id', '=', rec.request_employee_id.id), ('state', 'in', ['open', 'pending'])])
    #             if not obj_contract_isya:
    #                 raise ValidationError(_("There has no open/renew contract of ISYA for this requested employee."))
    #             if not obj_contract_gty:
    #                 raise ValidationError(_("There has no open/renew contract of GTY for this requested employee."))
    #             obj_contracts = {'gty':obj_contract_gty, 'isya':obj_contract_isya}
    #         else: # Local
    #             obj_contract_gty = rec.env['hr.contract'].sudo().search(
    #                 [('company_id.parent_id','!=',False),('employee_id', '=', rec.request_employee_id.id), ('state', 'in', ['open', 'pending'])])
    #             obj_contract_isya = rec.env['hr.contract']
    #             if not obj_contract_gty:
    #                 raise ValidationError(_("There has no open/renew contract for this requested employee."))
    #             obj_contracts = {'gty':obj_contract_gty, 'isya':obj_contract_isya}
    #         if len(obj_contract_isya) > 1 or len(obj_contract_gty) > 1:
    #             raise UserError(_("Please check contracts because there has more than one opening/renew contract."))
            
    #         return obj_contracts


    def get_contract(self):
        for rec in self:
            is_local = 'Local' in rec.request_employee_id.sudo().category_ids.sudo().mapped('name')

            _logger.info(f"Processing employee {rec.request_employee_id.name}, Local: {is_local}")

            obj_contract_isya = rec.env['hr.contract']
            obj_contract_gty = rec.env['hr.contract']

            if not is_local:  # Expat - ISYA
                obj_contract_isya = rec.env['hr.contract'].sudo().search([
                    ('company_id.short_name', '=', 'ISYA'),
                    ('employee_id', '=', rec.request_employee_id.id),
                    ('state', 'in', ['open', 'pending'])
                ])
                obj_contract_gty = rec.env['hr.contract'].sudo().search([
                    ('company_id.short_name', '=', 'GTY'),
                    ('employee_id', '=', rec.request_employee_id.id),
                    ('state', 'in', ['open', 'pending'])
                ])

                _logger.info(f"Expat Contracts -> ISYA: {len(obj_contract_isya)}, GTY: {len(obj_contract_gty)}")

                if not obj_contract_isya:
                    raise ValidationError(_("There is no open/renew contract of ISYA for this requested employee."))
                if not obj_contract_gty:
                    raise ValidationError(_("There is no open/renew contract of GTY for this requested employee."))

            else:  # Local
                obj_contract_gty = rec.env['hr.contract'].sudo().search([
                    ('company_id.short_name', '=', 'GTY'),
                    ('employee_id', '=', rec.request_employee_id.id),
                    ('state', 'in', ['open', 'pending'])
                ])

                _logger.info(f"Local Contracts -> GTY: {len(obj_contract_gty)}")

                if not obj_contract_gty:
                    raise ValidationError(_("There is no open/renew contract for this requested employee."))

            obj_contracts = {'gty': obj_contract_gty, 'isya': obj_contract_isya}

            if len(obj_contract_isya) > 1 or len(obj_contract_gty) > 1:
                raise UserError(_("Please check contracts because there is more than one open/renew contract."))

            return obj_contracts


  
    def process_approved(self):
        for rec in self:
            if rec.env.user.id == rec.approval_person.user_id.id:
                obj_contract = rec.get_contract()
                if not rec.is_after_lastday:
                    rec._process_approved_toupdate()
                else:
                    next_som = ((rec.requested_date+relativedelta(months=1)).replace(day=1)).date()
                    if datetime.now().date() >= next_som: # approve at the next month
                        rec._process_approved_toupdate()
                rec.state = 'done'
            else:
                raise ValidationError(
                    _("You are not allowed to approve this!"))

    def cron_process_approved(self):
        records = self.search([('state','=','done'),('is_after_lastday','=',True)])
        records._process_approved_toupdate()

    def _process_approved_toupdate(self):
        for rec in self:
            employee_type = 'local' if 'Local' in [
                x.name for x in self.request_employee_id.sudo().category_ids.sudo()] else 'expatriate'
            
            obj_contracts = rec.get_contract()
            obj_contract_gty = obj_contracts.get('gty')
            obj_contract_isya = obj_contracts.get('isya')
            for car in rec.cash_allocation_requests:
                if car.name == 'local_bank_$':
                    if employee_type == 'local':
                        obj_contract_gty.x_studio_local_bank = car.amount * -1
                        obj_contract_isya.x_studio_local_bank = 0
                    else:
                        obj_contract_isya.x_studio_local_bank = car.amount * -1
                        obj_contract_gty.x_studio_local_bank = 0
                elif car.name == 'local_bank_mmk':
                    obj_contract_isya.local_bank_mmk = car.amount * -1
                elif car.name == 'local_bank_ks':
                    obj_contract_isya.x_studio_local_bank_k = car.amount * -1
                elif car.name == 'cash_usd':
                    obj_contract_isya.cash_usd = car.amount * -1
                elif car.name == 'petty_cash_$':
                    obj_contract_isya.x_studio_petty_cash =  car.amount * -1
                elif car.name == '401_k':
                    obj_contract_isya.x_studio_401k = car.amount * -1
                elif car.name == 'overseas_bank':
                    obj_contract_isya.x_studio_overseas_bank = car.amount * -1
                # elif car.name == 'donation_uws':
                #     obj_contract_isya.donation_uws = car.amount * -1
                # elif car.name == 'donation_clc':
                #     obj_contract_isya.donation_clc = car.amount * -1
                # elif car.name == 'donation_yas':
                #     obj_contract_isya.donation_yas = car.amount * -1
                elif car.name == 'donation_chinthe':
                    obj_contract_isya.donation_chinthe = car.amount * -1
                elif car.name == 'gala_usd':
                    obj_contract_isya.gala_usd = car.amount * -1
                elif car.name == 'savings_for_education': # GTY
                    obj_contract_gty.savings_for_education = car.amount * -1
                    obj_contract_isya.savings_for_education = 0

            # these donations are not used anymore.
            obj_contract_isya.donation_uws = 0
            obj_contract_isya.donation_clc = 0
            obj_contract_isya.donation_yas = 0

            obj_contract_gty.local_bank_mmk = 0
            obj_contract_gty.x_studio_local_bank_k = 0
            obj_contract_gty.cash_usd = 0
            obj_contract_gty.x_studio_petty_cash =  0
            obj_contract_gty.x_studio_401k = 0
            obj_contract_gty.x_studio_overseas_bank = 0
            obj_contract_gty.donation_uws = 0
            obj_contract_gty.donation_clc = 0
            obj_contract_gty.donation_yas = 0
            obj_contract_gty.donation_chinthe = 0
            obj_contract_gty.gala_usd = 0
            
            val_list = []
            val = {}
            for bank in rec.bank_details:
                val = {
                    'employee_id': bank.employee_id.id,
                    'account_type': bank.account_type,
                    'behalf_of': bank.behalf_of,
                    'name': bank.name,
                    'account_number': bank.account_number,
                    'bank_name': bank.bank_name,
                    'routing': bank.routing,
                    'name_address': bank.name_address,
                    'name_bank_address': bank.name_bank_address,
                    'special_instruction': bank.special_instruction,
                    'attachment_1': bank.attachment_1,
                    'attachmet_1_name': bank.attachmet_1_name,
                    'other': bank.other,
                    'notes': bank.notes,
                    'attachment_2': bank.attachment_2,
                    'attachmet_2_name': bank.attachmet_2_name,
                    'time_of_entry': rec.requested_date,
                }
                val_list.append(val)
            self.env['hr.employee.bank.report'].create(val_list)
            rec.update({'is_after_lastday':False,'msg_validation':False})

    def reset_draft(self):
        for rec in self:
            rec.requested_date = datetime.now()
            first_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.first_request_day', 1)
            first_request_date = fields.Date().today().replace(day=int(first_day))
            last_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.last_request_day', 20)
            last_request_date = fields.Date().today().replace(day=int(last_day))

            # deadline for Local
            is_expat = False if 'Local' in [
                    x.name for x in rec.request_employee_id.sudo().category_ids.sudo()] else True
            if not is_expat:
                first_request_date = fields.Date().today().replace(day=1)
                last_request_date = fields.Date().today().replace(day=10)

            if rec.requested_date.date() >= first_request_date and rec.requested_date.date() <= last_request_date:
                rec.is_after_lastday = False
                rec.msg_validation = False
            else:
                rec.is_after_lastday = True
                rec.msg_validation = "This request will be reflected in the next month's payroll."
                # raise ValidationError(
                #     _("You cannot make changes to this record between " + str(first_day) + " and " + str(last_day) + " of the month."))           
            rec.state = 'draft'

    def write(self, values):
        if self.state == 'draft':
            values['state'] = 'waitingforapproval'
        result = super(HrPayslipProcessRequest, self).write(values)
        self.check_allocation_request()
        return result

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'hr.payslip.process.request') or 'New'
        vals['state'] = 'waitingforapproval'
        if not vals['request_employee_id']:
            raise ValidationError(_("Please contact to odoo admin as your account is not link with employee informatin yet. \n Please click 'Discard' button."))
        first_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.first_request_day', 1)
        first_request_date = fields.Date().today().replace(day=int(first_day))
        last_day = self.env['ir.config_parameter'].sudo().get_param('mt_isy.last_request_day', 20)
        last_request_date = fields.Date().today().replace(day=int(last_day))

        # deadline for Local
        is_expat = False if 'Local' in [
                x.name for x in self.env['hr.employee'].sudo().browse((vals.get('request_employee_id') or False)).sudo().category_ids.sudo()] else True
        if not is_expat:
            first_request_date = fields.Date().today().replace(day=1)
            last_request_date = fields.Date().today().replace(day=10)

        # obj_payslip_process = self.env['hr.payslip.process.request'].search([('state', '=', 'done'), ('request_employee_id', '=', vals['request_employee_id']), (
        #     'create_date', '>', str(first_request_date)+' 00:00:01'), ('create_date', '<', str(last_request_date)+' 23:59:59')])
        # if obj_payslip_process:
        #     raise ValidationError(_("Please find your record for this month and modify on this by clicking 'Reset to Draft'."))
        
        if datetime.now(timezone('Asia/Rangoon')).date() >= first_request_date and datetime.now(timezone('Asia/Rangoon')).date() <= last_request_date:
            result = super(HrPayslipProcessRequest, self).create(vals)
            result.check_allocation_request()
            return result
        else:
            is_after_lastday = True
            msg_validation = "This request will be reflected in the next month's payroll."
            # raise ValidationError(_("Please make your request days between " + str(first_day) + " and " + str(last_day) + " of the month."))
            vals.update({'is_after_lastday':is_after_lastday, 'msg_validation':msg_validation})
            result = super(HrPayslipProcessRequest, self).create(vals)
            result.check_allocation_request()
            return result

    @api.onchange('request_employee_id')
    def _create_cash_allocation_requests(self):
        if self.request_employee_id:
            self.cash_allocation_requests = False
            self.deduction_details = False
            cash_allocation_list = []
            obj_contracts = self.get_contract()
            employee_type = 'local' if 'Local' in [
                x.name for x in self.request_employee_id.sudo().category_ids.sudo()] else 'expatriate'
            if employee_type == 'local':
                obj_contract_gty = obj_contracts.get('gty')
                obj_contract_isya = obj_contracts.get('isya')
                functional_rate = self.env['res.currency'].search([('name','=','MMK')]).functional_rate
                monthly_salary_gty = obj_contract_gty.x_studio_monthly_salary - (obj_contract_gty.x_studio_income_tax/functional_rate)
                #monthly_retirement_gty = obj_contract_gty.x_studio_local_monthly_retirement_1
                monthly_retirement_gty = 0
                monthly_retirement_isya = 0
                for key, val in CASH_ALLOCATION_TYPE:
                    if key in ('local_bank_$','petty_cash_$'):
                        if key == 'local_bank_$':
                            amount = obj_contract_gty.x_studio_local_bank * -1
                            continue
                        elif key == 'petty_cash_$':
                            amount = obj_contract_gty.x_studio_petty_cash * -1
                        # elif key == 'overseas_bank':
                        #     amount = obj_contract.x_studio_overseas_bank  * -1
                        result = (0, 0, {
                            'name': key,
                            'amount': amount,
                        })
                        cash_allocation_list.append(result)
            else:
                obj_contract_gty =  obj_contracts.get('gty')
                obj_contract_isya = obj_contracts.get('isya')
                monthly_salary_gty = obj_contract_gty.x_studio_monthly_salary
                monthly_retirement_gty = obj_contract_gty.x_studio_expatriate_monthly_retirement
                monthly_retirement_isya = obj_contract_isya.x_studio_expatriate_monthly_retirement
                for key, val in CASH_ALLOCATION_TYPE:
                    # if key in ('gala_usd','donation_chinthe','donation_clc','donation_uws','donation_yas','local_bank_ks','cash_usd','local_bank_mmk', 'local_bank_$', '401_k', 'petty_cash_$'):
                     if key in ('donation_chinthe','donation_clc','donation_uws','donation_yas','local_bank_ks','cash_usd','local_bank_mmk', 'local_bank_$', '401_k', 'petty_cash_$'):
                    #if key in ('donation_chinthe','donation_clc','donation_uws','donation_yas','local_bank_ks','cash_usd','local_bank_mmk', '401_k', 'petty_cash_$'):
                        website_url = ''
                        if key == 'local_bank_$':
                            amount = obj_contract_isya.x_studio_local_bank * -1
                        elif key == 'local_bank_mmk':
                            amount = obj_contract_isya.local_bank_mmk * -1
                        elif key == 'local_bank_ks':
                            amount = obj_contract_isya.x_studio_local_bank_k * -1
                        elif key == 'cash_usd':
                            amount = obj_contract_isya.cash_usd * -1
                        elif key == 'petty_cash_$':
                            amount = obj_contract_isya.x_studio_petty_cash * -1

                        elif key == '401_k':
                            amount = obj_contract_isya.x_studio_401k * -1
                        elif key == 'donation_uws':
                            continue
                        #     amount = obj_contract_isya.donation_uws * -1
                        #     website_url = 'https://isyedu.org/support-isy/isy-partner-projects/'
                        elif key == 'donation_clc':
                            continue
                            amount = obj_contract_isya.donation_clc * -1
                            website_url = 'https://isyedu.org/support-isy/isy-partner-projects/'
                        elif key == 'donation_yas':
                            continue
                            amount = obj_contract_isya.donation_yas * -1
                            website_url = 'https://isyedu.org/support-isy/isy-partner-projects/'
                        elif key == 'donation_chinthe':
                            amount = obj_contract_isya.donation_chinthe * -1
                            website_url = 'https://isyedu.org/support-isy/isy-partner-projects/'
                        elif key == 'gala_usd':
                            # continue
                            amount = obj_contract_isya.gala_usd * -1
                        
                        result = (0, 0, {
                            'name': key,
                            'amount': amount,
                            'website_url': website_url,
                        })
                        cash_allocation_list.append(result)
            if self.request_employee_id.sudo().is_scholarship_staff:
                result = (0, 0, {
                    'name': 'savings_for_education',
                    'amount': 0, #obj_contract_gty.savings_for_education * -1,
                    'website_url': '',
                })
                cash_allocation_list.append(result)
            deduction_list = [(0,0, {
                'amount': 0.0
            })]

            # monthly_salary_gty = obj_contract_gty.x_studio_monthly_salary
            monthly_salary_isya = obj_contract_isya.x_studio_monthly_salary

            allowance_utility = obj_contract_isya.allowance_utility #+obj_contract_gty.allowance_utility

            self.monthly_salary_gty = monthly_salary_gty
            self.monthly_salary_isya = monthly_salary_isya
            self.retirement_salary_gty = monthly_retirement_gty
            self.retirement_salary_isya = monthly_retirement_isya

            self.monthly_salary = monthly_salary_gty+monthly_salary_isya
            self.retirement_salary = monthly_retirement_gty+monthly_retirement_isya

            self.total_salary = monthly_salary_gty+monthly_salary_isya+monthly_retirement_gty+monthly_retirement_isya+allowance_utility
            self.cash_allocation_requests = cash_allocation_list
            self.deduction_details = deduction_list

            self.allowance_utility = allowance_utility

class HrPayslipCashAllocationRequests(models.Model):
    _name = 'hr.payslip.cash.allocation.requests'

    @api.depends('name')
    def compute_name_url(self):
        for rec in self:
            name = dict(rec._fields.get('name').selection).get(rec.name) or ''
            if 'donation' in rec.name:
                # rec.name_url = '<p>Donation to <u><strong><a href="https://isyedu.org/support-isy/isy-partner-projects/" target="_blank">Chinthe Fund</a></strong></u></p>'
                rec.name_url = '<p>Donation to <strong><a href="https://isyedu.org/support-isy/isy-partner-projects/" target="_blank"><u>Chinthe Fund</u></a></strong></p>'
            else:
                rec.name_url = '<p>'+name+'</p>'

    name = fields.Selection(CASH_ALLOCATION_TYPE, string="Type")
    name_url = fields.Html(string='Type',compute='compute_name_url')
    hr_payslip_process_request_id = fields.Many2one('hr.payslip.process.request', string="HR Payslip Process Request")
    amount = fields.Float(string="Amount")
    note = fields.Text(string = "Note")
    attachment_1 = fields.Binary(string="Attachment 1", attachment=True)
    attachmet_1_name = fields.Char(string="Attachment 1 Name")
    attachment_2 = fields.Binary(string="Attachment 2", attachment=True)
    attachmet_2_name = fields.Char(string="Attachment 2 Name")
    website_url = fields.Char('Website Link')
    

class HrPayslipDeductionDetails(models.Model):
    _name = 'hr.payslip.deduction.details'

    name = fields.Char(string="Description")
    hr_payslip_deduction_request_id = fields.Many2one(
        'hr.payslip.process.request', string="HR Payslip Process Request")
    employee_id = fields.Many2one('hr.employee', related='hr_payslip_deduction_request_id.request_employee_id')
    deduction_type = fields.Selection([('school_trip', 'School Trip'), ('tuition_fee', 'Tuition Fee'), ('other', 'Other')], string="Type")
    amount = fields.Float(string="Amount (USD)")
    attachment_1 = fields.Binary(string="Attachment 1", attachment=True)
    attachmet_1_name = fields.Char(string="Attachment 1 Name")
    attachment_2 = fields.Binary(string="Attachment 2", attachment=True)
    attachmet_2_name = fields.Char(string="Attachment 2 Name")
   

    @api.constrains('amount')
    def _validate_negative_amount(self):
        for rec in self:
            if rec.amount < 0:
                raise ValidationError(_('In "Adjustment Details", deduction amount is not allowed to add negative sign.'))
            if not rec.deduction_type and rec.amount > 0:
                raise ValidationError(
                    _('Please choose type from adjustment request.'))


class HrPayslipBankDetails(models.Model):
    _name = 'hr.payslip.bank.details'

    employee_id = fields.Many2one('hr.employee', related='hr_payslip_bank_request_id.request_employee_id', string="Employee")
    account_type = fields.Char(string = "Account Type")
    behalf_of = fields.Char(string = "Behalf of")
    name = fields.Char(string = "Beneficiary Name")
    account_number = fields.Char(string="Account Number")
    bank_name = fields.Char(string = "Bank Name")
    routing = fields.Char(string="Routing/SWIFT/BIC")
    name_address = fields.Text(string="Beneficiary address")
    name_bank_address = fields.Text(string="Beneficiary Bank address")
    special_instruction = fields.Text(string="Special Instruction")
    attachment_1 = fields.Binary(string="Attachment 1", attachment=True)
    attachmet_1_name = fields.Char(string="Attachment 1 Name")
    other = fields.Char(string = "Other")
    notes = fields.Text(string="Notes and Instructions")
    attachment_2 = fields.Binary(string="Attachment 2", attachment=True)
    attachmet_2_name = fields.Char(string="Attachment 2 Name")
    hr_payslip_bank_request_id = fields.Many2one('hr.payslip.process.request')


class HrEmployeeBankReport(models.Model):
    _name = 'hr.employee.bank.report'

    employee_id = fields.Many2one('hr.employee', string="Employee")
    account_type = fields.Char(string = "Account Type")
    behalf_of = fields.Char(string = "Behalf of")
    name = fields.Char(string = "Beneficiary Name")
    account_number = fields.Char(string="Account Number")
    bank_name = fields.Char(string = "Bank Name")
    routing = fields.Char(string="Routing/SWIFT/BIC")
    name_address = fields.Text(string="Beneficiary address")
    name_bank_address = fields.Text(string="Beneficiary Bank address")
    special_instruction = fields.Text(string="Special Instruction")
    other = fields.Char(string = "Other")
    notes = fields.Text(string="Notes and Instructions")
    attachment_1 = fields.Binary(string="Attachment 1", attachment=True)
    attachmet_1_name = fields.Char(string="Attachment 1 Name")
    attachment_2 = fields.Binary(string="Attachment 2", attachment=True)
    attachmet_2_name = fields.Char(string="Attachment 2 Name")
    time_of_entry = fields.Datetime(string="Time of Entry")

class HrContract(models.Model):
    _inherit = 'hr.contract'

    local_bank_mmk = fields.Float(string='Amount in USD to be deposited into Kyat bank account')
    cash_usd = fields.Float(string='Amount in USD to be paid in USD cash')
    extra_duty_allw = fields.Float(string="Extra Duty Allowance(%)")
    allowance_utility = fields.Float('Utility Allowance')

    # Tax Calculation
    home_allw = fields.Float(string="Home Allowance (5)")
    other_allw = fields.Float(string="Other Allowance (6)")
    total_allw = fields.Float(string="Total (4+5+6)")#,compute="compute_tax",store=True)
    basic_relief = fields.Float(string="Basic Relief (8)")#,compute="compute_tax",store=True)
    pension_allw = fields.Float(string="Pension Allowance (9)")
    lifeinsurance_allw = fields.Float(string="Life Insurance Premium Allowance (10)")
    otherlaw_allw = fields.Float(string="Other Savings as per Law (11)")
    total_relief = fields.Float(string="Total Relief (15)")#,compute="compute_tax",store=True)
    taxable_amount = fields.Float(string="Taxable Amount (16)")#,compute="compute_tax",store=True)
    yearly_income_tax = fields.Float(string="Yearly Income Tax (MMK) (17)")#,compute="compute_tax",store=True)
    remark_fortax = fields.Text(string="Remark")

    unpaid_retirement = fields.Boolean('Without Retirement',default=False,help="Payslip Approval will be requested without retirement for this employee.")
    donation_uws = fields.Float(string='United World Schools')
    donation_clc = fields.Float(string='Care to the Least Center - CLC Family')
    donation_yas = fields.Float(string='Yangon Animal Shelter')
    donation_chinthe = fields.Float(string='Chinthe Fund')
    gala_usd = fields.Float(string="Amount in USD to pay for ISY Gala Ticket(s) - $50 Each")

    company_id = fields.Many2one('res.company', compute='', store=True, readonly=False,
        default=lambda self: self.env.company, required=True)

    savings_for_education = fields.Float('Saving for Children Education')

    @api.depends('employee_id')
    def _compute_employee_contract(self):
        for contract in self.filtered('employee_id'):
            contract.job_id = contract.employee_id.job_id
            contract.department_id = contract.employee_id.department_id
            contract.resource_calendar_id = contract.employee_id.resource_calendar_id
            # contract.company_id = contract.employee_id.company_id

    #@api.depends('x_studio_to_calculate')
    def compute_tax(self):
        for rec in self:
            mmk_currency = self.env['res.currency'].sudo().search([('name','=','MMK')])
            # func_rate = mmk_currency.functional_rate
            emp_obj = rec.employee_id
            if 'Local' in emp_obj.sudo().category_ids.mapped('name'):
                func_rate = 1560
            else:
                func_rate = 2100
            # input
            home_allw = rec.home_allw 
            other_allw = rec.other_allw 
            pension_allw = rec.pension_allw 
            lifeinsurance_allw = rec.lifeinsurance_allw
            otherlaw_allw = rec.otherlaw_allw
            spousetax_allw = rec.x_studio_spouse_allowance
            child_allw = 500000 * int(rec.x_studio_registered_child)
            parent_allw = 1000000 * int(rec.x_studio_registered_parent)


            wage = rec.x_studio_to_calculate
            wage_mmk = wage * func_rate
            # No 7
            wage_mmk = wage_mmk + home_allw + other_allw
            rec.total_allw = wage_mmk
            # No 8
            basic_relief = round(wage_mmk*20/100.0) if ((wage_mmk*20/100.0)<10000000) else 10000000
            rec.basic_relief = basic_relief
            # No15
            total_relief = basic_relief+pension_allw+lifeinsurance_allw+otherlaw_allw+spousetax_allw+child_allw+parent_allw
            rec.total_relief = total_relief
            # No 16
            taxable_income = round(wage_mmk-total_relief) if ((wage_mmk-total_relief)>0) else 0
            rec.taxable_amount = taxable_income
            # No 17
            """
            0% => 1 ~ 2000000
            5% => 2000001 ~ 5000000
            10% => 5000001 ~ 10000000
            15% => 10000001 ~ 20000000
            20% => 20000001 ~ 30000000
            25% => 30000001 ~ 
            """
            tax_amount = 0
            if taxable_income > 2000000: #5%
                tax_amount += ((5000000 if taxable_income>5000000 else taxable_income)-2000000) * 5/100.0
            if taxable_income > 5000000: # 10%
                tax_amount += ((10000000 if taxable_income>10000000 else taxable_income)-5000000) * 10/100.0
            if taxable_income >10000000: #15%
                tax_amount += ((20000000 if taxable_income>20000000 else taxable_income)-10000000) * 15/100.0
            if taxable_income >20000000: # 20%
                tax_amount += ((30000000 if taxable_income>30000000 else taxable_income)-20000000) * 20/100.0
            if taxable_income >30000000: # 25%
                tax_amount += (taxable_income-30000000) * 25/100.0
            if 'Local' in emp_obj.sudo().category_ids.mapped('name'): # for 6 months
                rec.x_studio_income_tax = round(tax_amount/12.0/2,2)
            else:
                rec.x_studio_income_tax = round(tax_amount/12.0,2)
            rec.yearly_income_tax = tax_amount



    def get_emails_list(self, val):
        email_ids = ''
        if val == 'annual_salary':
            user_ids = self.env.ref(
                'mt_isy.group_isy_annual_salary_modify_reminder').users
            for user_id in user_ids:
                if not user_id.partner_id.email == 'odooadmin@isyedu.org':
                    email_ids += str(user_id.partner_id.email) + ','
            return email_ids

    @api.model
    def create(self, values):
        res = super(HrContract, self).create(values)
        if res.wage and res.wage > 0:
            template = self.env.ref('mt_isy.group_isy_annual_salary_modify_reminder_mail_template')
            self.env['mail.template'].browse(template.id).sudo().send_mail(res.id)
        return res

    def write(self, values):
        send_mail = False
        if 'wage' in values.keys():
            if self.wage != values['wage']:
                send_mail = True
        res = super(HrContract, self).write(values)
        if send_mail==True:
            template = self.env.ref('mt_isy.group_isy_annual_salary_modify_reminder_mail_template')
            self.env['mail.template'].browse(template.id).sudo().send_mail(self.id)
        return res

    def _get_occupation_dates(self, include_future_contracts=False):
        # Takes several contracts and returns all the contracts under the same occupation (i.e. the same
        #  work rate + the date_from and date_to)
        # include_futur_contracts will use draft contracts if the start_date is posterior compared to current date
        #  NOTE: this does not take kanban_state in account
        result = []
        done_contracts = self.env['hr.contract']
        date_today = fields.Date.today()
        for contract in self:
            if contract in done_contracts:
                continue
            contracts = contract  # hr.contract(38,)
            date_from = contract.date_start
            date_to = contract.date_end
            history = self.env['hr.contract.history'].search([('employee_id', '=', contract.employee_id.id)], limit=1)
            all_contracts = history.sudo().contract_ids.filtered(
                lambda c: (
                    c.company_id.id in self.env.companies.ids and
                    c.active and c != contract and
                    (c.state in ['open', 'close'] or (include_future_contracts and c.state == 'draft' and c.date_start >= date_today))
                )
            ) # hr.contract(29, 37, 38, 39, 41) -> hr.contract(29, 37, 39, 41)
            before_contracts = all_contracts.filtered(lambda c: c.date_start < contract.date_start) # hr.contract(39, 41)
            after_contracts = all_contracts.filtered(lambda c: c.date_start > contract.date_start).sorted(key='date_start') # hr.contract(37, 29)

            for before_contract in before_contracts:
                if contract._is_same_occupation(before_contract):
                    date_from = before_contract.date_start
                    contracts |= before_contract
                else:
                    break

            for after_contract in after_contracts:
                if contract._is_same_occupation(after_contract):
                    date_to = after_contract.date_end
                    contracts |= after_contract
                else:
                    break
            result.append((contracts, date_from, date_to))
            done_contracts |= contracts
        return result


class HrWorkEntryRegenerationWizard(models.TransientModel):
    _inherit = 'hr.work.entry.regeneration.wizard'

    @api.depends('employee_ids')
    def _compute_earliest_available_date(self):
        for wizard in self:
            dates = wizard.sudo().mapped('employee_ids.contract_ids.date_generated_from')
            wizard.earliest_available_date = min(dates) if dates else None
