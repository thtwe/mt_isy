# -*- coding: utf-8 -*-
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
import logging
_logger = logging.getLogger(__name__)

class ExtendedBudgetOpeningEntry(models.TransientModel):
    _name = 'extended.budget.opening.entry'



    name = fields.Many2one(
        'account.fiscal.year', string="Carry Budget Template From", required="1")
    name_for = fields.Many2one(
        'account.fiscal.year', string="Create Budget Template For", required="1")
    entry_details = fields.One2many(
        'extended.budget.opening.entry.details', 'entry_id', string="Opening Budget Name From Last Year")


    @api.onchange('name')
    def onchange_df_dt(self):
        if self.name:
            budget_lists = self.env['budgetextension.budget'].search([('start_date', '>=', str(
                self.name.date_from)), ('end_date', '<=', str(self.name.date_to))])
            result_list = [(5, 0, 0)]
            _logger.info("==========================================")
            _logger.info(len(budget_lists))
            _logger.info("==========================================")
            for budget in budget_lists:
                result_list.append((0, 0, {
                    'name': budget.id,
                    'account_id': budget.account_id.id,
                    'tax_currency_rate': budget.tax_currency_rate,
                    'x_studio_type': budget.x_studio_type,
                    'x_studio_group': budget.x_studio_group.id,
                }))
            self.update({'entry_details': result_list})


    def generate_extended_budget_opening_entry(self):
        result_list = []
        budget_lists = self.env['budgetextension.budget'].search([('start_date', '>=', str(
            self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))])
        if budget_lists:
            raise ValidationError(_("Budget already created for this year."))
        for rec in self.entry_details:
            result_list.append({
                'name': rec.name.name,
                'account_id': rec.account_id.id,
                'tax_currency_rate': rec.tax_currency_rate,
                'x_studio_type': rec.x_studio_type,
                'x_studio_group': rec.x_studio_group.id,
                'start_date':   self.name_for.date_from,
                'end_date': self.name_for.date_to,
                'planned_amount': 0,
                'planned_amount_100': 0,
                'company_id':self.env.company[0].id,
            })
        result = self.env['budgetextension.budget'].sudo().with_context(
            tracking_disable=True).create(result_list)
        return result



class ExtendedBudgetOpeningEntryDetails(models.TransientModel):
    _name = 'extended.budget.opening.entry.details'

    name = fields.Many2one('budgetextension.budget', string="Budget")
    entry_id = fields.Many2one('extended.budget.opening.entry')
    account_id = fields.Many2one('account.account', string="Account")
    tax_currency_rate = fields.Float(string="Tax Currency Rate")
    #x_studio_type = fields.Many2one("account.account.type", string="Type")
    x_studio_type = fields.Selection(
        string="Type", related="account_id.account_type")
    x_studio_group = fields.Many2one("x_grouping", string="Group")


class PayrollBudgetOpeningEntry(models.TransientModel):
    _name = 'payroll.budget.opening.entry'

    name = fields.Many2one(
        'account.fiscal.year', string="Carry Payroll Budget Template From", required="1")
    name_for = fields.Many2one(
        'account.fiscal.year', string="Create Payroll Budget Template For", required="1")
    payroll_entry_details = fields.One2many(
        'payroll.budget.opening.entry.details', 'payroll_entry_id', string="Opening Payroll Budget Name From Last Year")

    @api.onchange('name')
    def onchange_df_dt(self):
        if self.name:
            budget_lists = self.env['payroll.budget'].search([('from_date', '>=', str(
                self.name.date_from)), ('to_date', '<=', str(self.name.date_to))])
            result_list = [(5, 0, 0)]
            _logger.info("==========================================")
            _logger.info(len(budget_lists))
            _logger.info("==========================================")
            for budget in budget_lists:
                result_list.append((0, 0, {
                    'name': budget.id,
                    'budget_id': budget.budget_id.id,
                    'retirement_budget_id': budget.retirement_budget_id.id,
                    'provident_fund_budget_id': budget.provident_fund_budget_id.id,
                    'severance_allowance_budget_id': budget.gratuity_budget_id.id,
                    'contingency_percentage': budget.contingency_percentage,
                }))
            self.update({'payroll_entry_details': result_list})

    def generate_payroll_budget_opening_entry(self):
        result_list = []
        budget_lists = self.env['payroll.budget'].search([('from_date', '>=', str(
            self.name_for.date_from)), ('to_date', '<=', str(self.name_for.date_to))])
        #budget_lists_ids = self.env['payroll.budget'].search([('id', '=', '32')])
        if budget_lists:
            raise ValidationError(_("Payroll Budget already created for this year."))
        for rec in self.payroll_entry_details:
            val = {
                'name': rec.name.name,
                # 'budget_id': rec.budget_id.id,
                'budget_id': self.env['budgetextension.budget'].search([('account_id','=',rec.budget_id.account_id.id),('start_date', '=', str(
            self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))]).id,
                # 'retirement_budget_id': rec.retirement_budget_id.id,
                'retirement_budget_id': self.env['budgetextension.budget'].search([('account_id','=',rec.retirement_budget_id.account_id.id),('start_date', '>=', str(
            self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))]).id,
                # 'provident_fund_budget_id': rec.provident_fund_budget_id.id,
                'provident_fund_budget_id': self.env['budgetextension.budget'].search([('account_id','=',rec.provident_fund_budget_id.account_id.id),('start_date', '>=', str(
            self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))]).id,
                # 'gratuity_budget_id': rec.severance_allowance_budget_id.id,
                'gratuity_budget_id': self.env['budgetextension.budget'].search([('account_id','=',rec.severance_allowance_budget_id.account_id.id),('start_date', '>=', str(
            self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))]).id,
                'from_date':   self.name_for.date_from,
                'to_date': self.name_for.date_to,
                'contingency_percentage': rec.contingency_percentage,     
                'mt_new_feature': True,
            }
            rl_details = []
            for rec_line in rec.name.payroll_line_m_ids:
                # val_next_year_base = rec_line.next_year_base + \
                #     rec_line.next_year_tax_amount + rec_line.next_year_allowance
                val_next_year_base = sum(self.env['hr.contract'].sudo().search([('employee_id','=',rec_line.employee_id.id),('state','not in',('close','cancel'))]).mapped('x_studio_to_calculate'))

                if rec_line.employee_id.active==True and len(rec_line.employee_id.contract_ids)>0:
                    rl_details.append((0, 0, {
                            'employee_id': rec_line.employee_id.id,
                            'employee': rec_line.employee,
                            'position' : rec_line.position,
                            'employee_type': rec_line.employee_type,
                            'budget_id': rec_line.budget_id.id,
                            'current_year_base': val_next_year_base, #rec_line.next_year_base + rec_line.next_year_tax_amount + rec_line.next_year_allowance,
                            'current_year_tax_amount': 0,
                            'current_year_allowance' : 0,
                            'retirement_percentage': 0,#rec_line.retirement_percentage,
                            'provident_fund_percentage': rec_line.provident_fund_percentage,
                            'inflation': rec_line.inflation,
                            'next_year_origin': val_next_year_base, #rec_line.next_year_base + rec_line.next_year_tax_amount + rec_line.next_year_allowance,#rec_line.next_year_origin,
                            'next_year_base': val_next_year_base + (val_next_year_base*rec_line.inflation/100),
                            'additional_stipend': rec_line.additional_stipend,


                        }))
            
            val['payroll_line_m_ids'] = rl_details
            result_list.append(val)
        if result_list:
            result = self.env['payroll.budget'].sudo().with_context(
                tracking_disable=True).create(result_list)
            return result
        else:
            return True



class PayrollBudgetOpeningEntryDetails(models.TransientModel):
    _name = 'payroll.budget.opening.entry.details'

    name = fields.Many2one("payroll.budget",string="Name")
    budget_id = fields.Many2one('budgetextension.budget', string="Budget")
    retirement_budget_id = fields.Many2one(
        'budgetextension.budget', string="Retirement Budget")
    provident_fund_budget_id = fields.Many2one(
        'budgetextension.budget', string="Provident Fund Budget")
    severance_allowance_budget_id = fields.Many2one(
        'budgetextension.budget', string="Severance Allowance Budget")
    contingency_percentage = fields.Float(string="Contingency (%)")
    payroll_entry_id = fields.Many2one('payroll.budget.opening.entry', string="Payroll Budget Opening")


class RentalBudgetOpeningEntry(models.TransientModel):
    _name = 'rental.budget.opening.entry'

    name = fields.Many2one(
        'account.fiscal.year', string="Carry Budget Template From", required="1")
    name_for = fields.Many2one(
        'account.fiscal.year', string="Create Budget Template For", required="1")
    entry_details = fields.One2many(
        'rental.budget.opening.entry.details', 'rental_entry_id', string="Opening Budget Name From Last Year")

    @api.onchange('name')
    def onchange_df_dt(self):
        if self.name:
            budget_lists = self.env['rental.budget'].search([('from_date', '>=', str(
                self.name.date_from)), ('to_date', '<=', str(self.name.date_to))])
            result_list = [(5, 0, 0)]
            _logger.info("==========================================")
            _logger.info(len(budget_lists))
            _logger.info("==========================================")
            for budget in budget_lists:
                result_list.append((0, 0, {
                    'name': budget.id,
                }))
            if result_list:
                self.update({'entry_details': result_list})


    def generate_rental_budget_opening_entry(self):
        result_list = []
        budget_lists = self.env['rental.budget'].search([('from_date', '>=', str(
            self.name_for.date_from)), ('to_date', '<=', str(self.name_for.date_to))])
        #budget_lists_ids = self.env['payroll.budget'].search([('id', '=', '32')])
        if budget_lists:
            raise ValidationError(
                _("Rental Budget already created for this year."))
        for rec in self.entry_details:
            new_budget_id = self.env['budgetextension.budget'].search([('name', '=', rec.name.budget_id.name), ('start_date', '>=', str(
                self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))])
            if not new_budget_id:
                raise ValidationError(
                    _("Extended Budget is not created for this year."))
            val = {
                'name': rec.name.name,
                'budget_id': new_budget_id.id,
                'from_date':   self.name_for.date_from,
                'to_date': self.name_for.date_to,
                'contingency_percentage': rec.name.contingency_percentage,
            }
            rl_details = []
            for rec_line in rec.name.rental_line_ids:
                rl_details.append((0, 0, {
                    'employee_id': rec_line.employee_id.id,
                    'categ_id': rec_line.categ_id.id,
                    'monthly_allowance': rec_line.monthly_allowance,
                    'annual_allowance': rec_line.annual_allowance,
                    'actual_monthly_rent': rec_line.actual_monthly_rent,
                }))
            val['rental_line_ids'] = rl_details
            result_list.append(val)
        if result_list:
            result = self.env['rental.budget'].sudo().with_context(
                tracking_disable=True).create(result_list)
            return result
        else:
            return True

class RentalBudgetOpeningEntryDetails(models.TransientModel):
    _name = 'rental.budget.opening.entry.details'

    name = fields.Many2one('rental.budget', string="Budget")
    rental_entry_id = fields.Many2one('rental.budget.opening.entry')


class CapitalBudgetOpeningEntry(models.TransientModel):
    _name = 'capital.budget.opening.entry'

    name = fields.Many2one(
        'account.fiscal.year', string="Carry Budget Template From", required="1")
    name_for = fields.Many2one(
        'account.fiscal.year', string="Create Budget Template For", required="1")
    entry_details = fields.One2many(
        'capital.budget.opening.entry.details', 'capital_entry_id', string="Opening Budget Name From Last Year")

    @api.onchange('name')
    def onchange_df_dt(self):
        if self.name:
            budget_lists = self.env['capital.budget.template'].search([('from_date', '>=', str(
                self.name.date_from)), ('to_date', '<=', str(self.name.date_to))])
            result_list = [(5, 0, 0)]
            _logger.info("==========================================")
            _logger.info(len(budget_lists))
            _logger.info("==========================================")
            for budget in budget_lists:
                result_list.append((0, 0, {
                    'name': budget.id,
                }))
            if result_list:
                self.update({'entry_details': result_list})

    def generate_capital_budget_opening_entry(self):
        result_list = []
        budget_lists = self.env['capital.budget.template'].search([('from_date', '>=', str(
            self.name_for.date_from)), ('to_date', '<=', str(self.name_for.date_to))])
        #budget_lists_ids = self.env['payroll.budget'].search([('id', '=', '32')])
        if budget_lists:
            raise ValidationError(
                _("Capital Budget already created for this year."))
        for rec in self.entry_details:
            val = {
                'name': rec.name.name,
                'from_date':   self.name_for.date_from,
                'to_date': self.name_for.date_to,
                'contingency_percentage': rec.name.contingency_percentage,
                'is_application': rec.name.is_application,
                'is_enrollment': rec.name.is_enrollment,
                'is_reserve': rec.name.is_reserve,
                'type_id': rec.name.type_id.id,
                'last_year_planned_amount': rec.name.planned_amount,
                'last_2_year_planned_amount': rec.name.last_year_planned_amount,
            }
            rl_details = []
            for rec_line in rec.name.capital_line_ids:
                rl_details.append((0, 0, {
                    'name': rec_line.name,
                    'total': rec_line.total,
                }))
            val['capital_line_ids'] = rl_details
            result_list.append(val)
        if result_list:
            result = self.env['capital.budget.template'].sudo().with_context(
                tracking_disable=True).create(result_list)
            return result
        else:
            return True


class CapitalBudgetOpeningEntryDetails(models.TransientModel):
    _name = 'capital.budget.opening.entry.details'

    name = fields.Many2one('capital.budget.template', string="Budget")
    capital_entry_id = fields.Many2one('capital.budget.opening.entry')


class RevenueBudgetYgnOpeningEntry(models.TransientModel):
    _name = 'revenue.budget.ygn.opening.entry'

    name = fields.Many2one(
        'account.fiscal.year', string="Carry Budget Template From", required="1")
    name_for = fields.Many2one(
        'account.fiscal.year', string="Create Budget Template For", required="1")
    entry_details = fields.One2many(
        'revenue.budget.ygn.opening.entry.details', 'revenue_ygn_entry_id', string="Opening Budget Name From Last Year")

    @api.onchange('name')
    def onchange_df_dt(self):
        if self.name:
            budget_lists = self.env['revenue.budget.ygn'].search([('from_date', '>=', str(
                self.name.date_from)), ('to_date', '<=', str(self.name.date_to))])
            result_list = [(5, 0, 0)]
            _logger.info("==========================================")
            _logger.info(len(budget_lists))
            _logger.info("==========================================")
            for budget in budget_lists:
                result_list.append((0, 0, {
                    'name': budget.id,
                }))
            if result_list:
                self.update({'entry_details': result_list})

    def generate_revenue_budget_ygn_opening_entry(self):
        result_list = []
        budget_lists = self.env['revenue.budget.ygn'].search([('from_date', '>=', str(
            self.name_for.date_from)), ('to_date', '<=', str(self.name_for.date_to))])
        #budget_lists_ids = self.env['payroll.budget'].search([('id', '=', '32')])
        if budget_lists:
            raise ValidationError(
                _("Revenue Budget YGN already created for this year."))
        for rec in self.entry_details:
            new_budget_id = self.env['budgetextension.budget'].search([('name', '=', rec.name.budget_id.name), ('start_date', '>=', str(
                self.name_for.date_from)), ('end_date', '<=', str(self.name_for.date_to))])
            if not new_budget_id:
                raise ValidationError(
                    _("Extended Budget is not created for this year."))
            val = {
                'budget_id': new_budget_id.id,
                'from_date':   self.name_for.date_from,
                'to_date': self.name_for.date_to,
                'current_year_student': rec.name.next_year_student,
                'current_year_fee': rec.name.next_year_fee,
                'current_year_total': rec.name.next_year_total,
                'percentage': rec.name.percentage,
                'next_year_student': 0,
                'next_year_fee': 0,
                'next_year_total': 0,
            }
           
            result_list.append(val)
        if result_list:
            result = self.env['revenue.budget.ygn'].sudo().with_context(
                tracking_disable=True).create(result_list)
            return result
        else:
            return True


class RevenueBudgetYgnOpeningEntryDetails(models.TransientModel):
    _name = 'revenue.budget.ygn.opening.entry.details'

    name = fields.Many2one('revenue.budget.ygn', string="Budget Grade")
    revenue_ygn_entry_id = fields.Many2one('revenue.budget.ygn.opening.entry')
