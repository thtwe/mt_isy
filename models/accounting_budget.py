# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from lxml import etree
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
# from odoo.osv.orm import setup_modifiers

class BudgetExtension_Budget(models.Model):
    _inherit = 'budgetextension.budget'

    company_id = fields.Many2one('res.company',string='Company',default=lambda self:self.env.user.company_id.id)

    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', toolbar=False,
                        submenu=False):
        result = super(BudgetExtension_Budget, self).fields_view_get(view_id,
                                                            view_type,
                                                            toolbar=toolbar,
                                                            submenu=submenu)
        doc = etree.XML(result['arch'])
        if view_type == 'tree' and self._module == 'mt_isy':
            #current view
            ref_view_id = self.env.ref('mt_isy.isy_budget_view_tree')
            last_year_ref_view_id = self.env.ref('mt_isy.all_year_isy_budget_view_tree')
            future_year_ref_view_id = self.env.ref('mt_isy.future_year_isy_budget_view_tree')
            if view_id == ref_view_id.id:
                val = self._get_year_from_to('current')
                #current year
                #planned amount
                planned_amount_100_reference = doc.xpath("//field[@name='planned_amount_100_neg']")
                planned_amount_100_reference[0].set(
                    "string", val['current_year'] + " - \n Budget (E)")

                #last year
                #planned amount
                last_year_planned_amount_100_reference = doc.xpath(
                    "//field[@name='x_last_year_planned_amount_100']")
                last_year_planned_amount_100_reference[0].set(
                    "string", val['last_year'] + " - \n Budget (C)")
               
                #last year
                #actual amount
                last_year_practical_amount_reference = doc.xpath(
                    "//field[@name='last_year_practical_amount_neg']")
                last_year_practical_amount_reference[0].set(
                    "string", val['last_year'] + " - \n Actual (D)")

                #last 2 year
                #planned amount
                last_2_year_planned_amount_100_reference = doc.xpath(
                    "//field[@name='last_2_year_planned_amount_100_neg']")
                last_2_year_planned_amount_100_reference[0].set(
                    "string", val['last_2_year'] + " - \n Budget (A) ")

                #last 2 year
                #actual amount
                last_2_year_practical_amount_reference = doc.xpath(
                    "//field[@name='last_2_year_practical_amount_neg']")
                last_2_year_practical_amount_reference[0].set(
                    "string", val['last_2_year'] + " - \n Actual (B)")
                result['arch'] = etree.tostring(doc, encoding='unicode')
           
            elif view_id == future_year_ref_view_id.id:
                val = self._get_year_from_to('future')
                #current year
                #planned amount
                planned_amount_100_reference = doc.xpath(
                    "//field[@name='planned_amount_100_neg']")
                planned_amount_100_reference[0].set(
                    "string", val['current_year'] + " - \n Budget (E)")

                #last year
                #planned amount
                last_year_planned_amount_100_reference = doc.xpath(
                    "//field[@name='x_last_year_planned_amount_100']")
                last_year_planned_amount_100_reference[0].set(
                    "string", val['last_year'] + " - \n Budget (C)")

                #last year
                #actual amount
                last_year_practical_amount_reference = doc.xpath(
                    "//field[@name='last_year_practical_amount_neg']")
                last_year_practical_amount_reference[0].set(
                    "string", val['last_year'] + " - \n Actual (D)")

                #last 2 year
                #planned amount
                last_2_year_planned_amount_100_reference = doc.xpath(
                    "//field[@name='last_2_year_planned_amount_100_neg']")
                last_2_year_planned_amount_100_reference[0].set(
                    "string", val['last_2_year'] + " - \n Budget (A) ")

                #last 2 year
                #actual amount
                last_2_year_practical_amount_reference = doc.xpath(
                    "//field[@name='last_2_year_practical_amount_neg']")
                last_2_year_practical_amount_reference[0].set(
                    "string", val['last_2_year'] + " - \n Actual (B)")
                result['arch'] = etree.tostring(doc, encoding='unicode')

        return result

    def _get_year_from_to(self, val):
        fd = self.env.user.company_id.fiscalyear_last_day
        fm = self.env.user.company_id.fiscalyear_last_month
        now = datetime.now()
        result = {}
        e_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (now.year, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            )
        if now.date() > e_fiscal_date.date():
            e_fiscal_date = datetime.strptime(
                "%s-%s-%s" % (now.year + 1, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            ) + timedelta(days=1)
        s_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        ) + timedelta(days=1)
        if val == 'current':            
            result = {
                'current_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_2_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],

            }
        elif val == 'last':
            result = {
                'current_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],
                'last_2_year': str(s_fiscal_date.date().year-3)[2::] + "/" + str(e_fiscal_date.date().year-3)[2::],

            }
        elif val == 'future':
            result = {
                'current_year': str(s_fiscal_date.date().year+1)[2::] + "/" + str(e_fiscal_date.date().year+1)[2::],
                'last_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_2_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],

            }
        elif val == 'date_from_to':
            result = {
                'date_from': s_fiscal_date.date(),
                'date_to': e_fiscal_date.date(),
            }
        return result

    @api.model
    def read_group(self, domain, fields, groupby, offset=0, limit=None, orderby=False, lazy=True):
        res = super(BudgetExtension_Budget, self).read_group(domain, fields, groupby,
                                             offset=offset, limit=limit, orderby=orderby, lazy=lazy)
        for line in res:
            if '__domain' in line:
                lines = self.search(line['__domain'])
                total_last_practical = 0.0
                total_last_planned_100 = 0.0
                
                total_last_2_practical = 0.0
                total_last_2_planned_100 = 0.0
                
                total_planned_100 = 0.0
                total_variance = 0.0
                for record in lines:
                    total_last_practical += record.last_year_practical_amount_neg
                    total_last_planned_100 += record.x_last_year_planned_amount_100
                    
                    total_last_2_practical += record.last_2_year_practical_amount_neg
                    total_last_2_planned_100 += record.last_2_year_planned_amount_100_neg
                    
                    total_planned_100 += record.planned_amount_100_neg
                    total_variance += record.last_year_variance_amount
                
                #last year actual
                line['last_year_practical_amount_neg'] = total_last_practical
                line['x_last_year_planned_amount_100'] = total_last_planned_100
                
                #last 2 year budget
                line['last_2_year_practical_amount_neg'] = total_last_2_practical
                #last 2 year actual
                line['last_2_year_planned_amount_100_neg'] = total_last_2_planned_100

                #current year budget
                line['planned_amount_100_neg'] = total_planned_100

                line['last_year_variance_amount'] = total_variance

        return res


class PayrollBudget(models.Model):
    _inherit = 'payroll.budget'

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        result = super(PayrollBudget, self).fields_view_get(view_id,
                                                                     view_type,
                                                                     toolbar=toolbar,
                                                                     submenu=submenu)
        doc = etree.XML(result['arch'])
        
        ref_view_id = self.env.ref('mt_isy.isy_payroll_budget_view_form')
        if view_type == 'form' and self._module == 'mt_isy':
            if view_id == ref_view_id.id:
                if not 'params' in self._context.keys():
                    return result
                if not 'id' in self._context.get('params').keys():
                    return result
                obj_budget = self.env['payroll.budget'].search(
                    [('id', '=', self._context.get('params')['id'] or False)])
                if obj_budget:
                    past_year = str(obj_budget.from_date.year - 1)[2::] + "/" + str(obj_budget.to_date.year - 1)[2::]
                else:
                    past_year = "Past Year"

                if obj_budget:
                    current_year = str(obj_budget.from_date.year)[
                        2::] + "/" + str(obj_budget.to_date.year)[2::]
                else:
                    current_year = "Current Year"
                
                if obj_budget and obj_budget.mt_new_feature == True: #For New Design

                    past_current_year_base = past_year + " - Base (A)"
                    
                    current_next_year_base = current_year + " - Base (C=A+(A*B/100)"
                    current_next_year_provident_fund = current_year + \
                        " - Provident Fund (E)"
                    current_next_year_gratuity_m = current_year + \
                        " - Retirement (D)"
                    current_next_year_budget = current_year + \
                        " - Budget (G=C+E+(C*F/100)|G=C+D+(C*F/100))"

                    current_next_year_gratuity_budget_line_percent = current_year + " Retirement %"
                    current_next_year_provident_fund_percentage = current_year + " Provident Fund %"

                    doc2 = etree.XML(
                        result['fields']['payroll_line_m_ids']['views']['tree']['arch'])
                    doc2 = """
                                <tree string="Payroll Lines" editable="bottom">

                                    <field name="employee_id"/>

                                    <field name="employee" required="1"/>
                                    <field name="position"/>
                                    <field name="employee_type" required="1"/>
                                    <field name="budget_id" string="Budget"/>

                                    <field name="current_year_base" string="20-21 Base (A)" sum="Total"/>
                                    <field name="inflation" string="Inflation % (B)"/>
                                    <field name="next_year_base" string="21-22 Base (C)" force_save="True" readonly="1" sum="Total"/>
                                    
                                    <field name="gratuity_budget_line_percent" string="Gratuity Budget Line %"/>

                                    <field name="next_year_gratuity_m" string="21-22 Gratuity(D))" sum="Total" force_save="True" readonly="1" />
                                    <field name="provident_fund_percentage" string="Provident Fund Percent"/>
                                    <field name="next_year_provident_fund" string="21-22 Provident Fund (E)"  readonly="1" sum="Total"/>
                                    <field name="additional_stipend" string="Additional Stipend % (F)"/>
                                    <field name="next_year_budget" string="21-22 Budget (G)"  readonly="1" sum="Total"/>

                                    <field name="variance" string="Variance (H=C-A)" sum="Total"/>
                                </tree>
                    """
                    result['fields']['payroll_line_m_ids']['views']['tree']['arch'] = doc2
                    
                    doc1 = etree.XML(
                        result['fields']['payroll_line_m_ids']['views']['tree']['arch'])

                    current_next_year_gratuity_budget_line_percent_ref = doc1.xpath("//field[@name='gratuity_budget_line_percent']")
                    current_next_year_gratuity_budget_line_percent_ref[0].set(
                        "string", current_next_year_gratuity_budget_line_percent)

                    current_next_year_provident_fund_percentage_ref = doc1.xpath("//field[@name='provident_fund_percentage']")
                    current_next_year_provident_fund_percentage_ref[0].set("string", current_next_year_provident_fund_percentage)


                    past_current_year_base_ref = doc1.xpath("//field[@name='current_year_base']")
                    past_current_year_base_ref[0].set("string", past_current_year_base)
                    past_current_year_base_ref[0].set('readonly', '0')
                    # setup_modifiers(past_current_year_base_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['current_year_base'])

                    current_next_year_base_ref = doc1.xpath("//field[@name='next_year_base']")
                    current_next_year_base_ref[0].set("string", current_next_year_base)
                    current_next_year_base_ref[0].set('readonly', '1')
                    # setup_modifiers(
                        # current_next_year_base_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['next_year_base'])
                    
                    current_next_year_gratuity_m_ref = doc1.xpath(
                        "//field[@name='next_year_gratuity_m']")
                    current_next_year_gratuity_m_ref[0].set(
                        "string", current_next_year_gratuity_m)
                    current_next_year_gratuity_m_ref[0].set('readonly', '1')
                    # setup_modifiers(
                        # current_next_year_gratuity_m_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['next_year_gratuity_m'])

                    
                    current_next_year_provident_fund_ref = doc1.xpath(
                        "//field[@name='next_year_provident_fund']")
                    current_next_year_provident_fund_ref[0].set(
                        "string", current_next_year_provident_fund)
                    current_next_year_provident_fund_ref[0].set(
                        'readonly', '1')
                    # setup_modifiers(
                        # current_next_year_provident_fund_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['next_year_provident_fund'])

                    current_next_year_budget_ref = doc1.xpath(
                        "//field[@name='next_year_budget']")
                    current_next_year_budget_ref[0].set(
                        "string", current_next_year_budget)
                    current_next_year_budget_ref[0].set(
                        'readonly', '1')
                    # setup_modifiers(
                        # current_next_year_budget_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['next_year_budget'])

                    variance_ref = doc1.xpath(
                        "//field[@name='variance']")
                    variance_ref[0].set(
                        'readonly', '1')
                    # setup_modifiers(
                        # variance_ref[0], result['fields']['payroll_line_m_ids']['views']['tree']['fields']['variance'])

                else:#For Old Design

                    past_current_year_base = past_year + " - Base"
                    past_current_year_retirement = past_year + \
                        " - Retirement(D=A*B)"
                    past_current_year_provident_fund = past_year + \
                        " - Provident Fund(E=A*C)"
                    past_current_year_budget = past_year + " - Budget(F=A+D|E)"
                    past_current_year_allowance = past_year + " - Allowance(Z)"
                    past_current_year_tax_amount = past_year + " - Tax(X)"


                    current_next_year_origin = current_year + " - Origin(G)"
                    current_next_year_base = current_year + " - Base(I=G+(G*H))"
                    current_next_year_base_additional = current_year + \
                        " - Base[Additional](K=I+(I*J))"
                    current_next_year_retirement = current_year + \
                        " - Retirement(L=I*B)"
                    current_next_year_provident_fund = current_year + \
                        " - Provident Fund(M=I*C)"
                    current_next_year_allowance = current_year + " - Allowance(N)"
                    current_next_year_gratuity_m = current_year + \
                        " - Severance Allowance(O=(N+K)*(SeveranceAllowanceBudgetPercent/100))"
                    current_next_year_tax_amount = current_year + " - Tax(P)"
                    current_next_year_net_income = current_year + \
                        " - Net Income(Q=(I+N+O)-P)"
                    current_next_year_net_budget = past_year + \
                        " - Net Budget(Y=F+" + past_year + "SeveranceAllowance+Z)"
                    current_next_year_budget = current_year + \
                        " - Budget(S=K+L|K+M+N+O)"

                    doc1 = etree.XML(
                        result['fields']['payroll_line_m_ids']['views']['tree']['arch'])

                    past_current_year_base_ref = doc1.xpath("//field[@name='current_year_base']")
                    past_current_year_base_ref[0].set("string", past_current_year_base)
                    
                    past_current_year_retirement_ref = doc1.xpath("//field[@name='current_year_retirement']")
                    past_current_year_retirement_ref[0].set("string", past_current_year_retirement)

                    past_current_year_provident_fund_ref = doc1.xpath(
                        "//field[@name='current_year_provident_fund']")
                    past_current_year_provident_fund_ref[0].set(
                        "string", past_current_year_provident_fund)

                    past_current_year_budget_ref = doc1.xpath(
                        "//field[@name='current_year_budget']")
                    past_current_year_budget_ref[0].set(
                        "string", past_current_year_budget)
                    
                    past_current_year_allowance_ref = doc1.xpath(
                        "//field[@name='current_year_allowance']")
                    past_current_year_allowance_ref[0].set(
                        "string", past_current_year_allowance)

                    past_current_year_tax_amount_ref = doc1.xpath(
                        "//field[@name='current_year_tax_amount']")
                    past_current_year_tax_amount_ref[0].set(
                        "string", past_current_year_tax_amount)
                    
                    current_next_year_origin_ref = doc1.xpath(
                        "//field[@name='next_year_origin']")
                    current_next_year_origin_ref[0].set(
                        "string", current_next_year_origin)

                    current_next_year_base_ref = doc1.xpath(
                        "//field[@name='next_year_base']")
                    current_next_year_base_ref[0].set(
                        "string", current_next_year_base)
                    
                                
                    current_next_year_base_additional_ref = doc1.xpath(
                        "//field[@name='next_year_base_additional']")
                    current_next_year_base_additional_ref[0].set(
                        "string", current_next_year_base_additional)
                    
                    current_next_year_retirement_ref = doc1.xpath(
                        "//field[@name='next_year_retirement']")
                    current_next_year_retirement_ref[0].set(
                        "string", current_next_year_retirement)

                    current_next_year_provident_fund_ref = doc1.xpath(
                        "//field[@name='next_year_provident_fund']")
                    current_next_year_provident_fund_ref[0].set(
                        "string", current_next_year_provident_fund)

                    current_next_year_allowance_ref = doc1.xpath(
                        "//field[@name='next_year_allowance']")
                    current_next_year_allowance_ref[0].set(
                        "string", current_next_year_allowance)
                    
                    current_next_year_gratuity_m_ref = doc1.xpath(
                        "//field[@name='next_year_gratuity_m']")
                    current_next_year_gratuity_m_ref[0].set(
                        "string", current_next_year_gratuity_m)

                    current_next_year_tax_amount_ref = doc1.xpath(
                        "//field[@name='next_year_tax_amount']")
                    current_next_year_tax_amount_ref[0].set(
                        "string", current_next_year_tax_amount)
                    
                    current_next_year_net_income_ref = doc1.xpath(
                        "//field[@name='next_year_net_income']")
                    current_next_year_net_income_ref[0].set(
                        "string", current_next_year_net_income)

                    current_next_year_net_budget_ref = doc1.xpath(
                        "//field[@name='current_year_net_budget']")
                    current_next_year_net_budget_ref[0].set(
                        "string", current_next_year_net_budget)

                    current_next_year_budget_ref = doc1.xpath(
                        "//field[@name='next_year_budget']")
                    current_next_year_budget_ref[0].set(
                        "string", current_next_year_budget)
                



                result['fields']['payroll_line_m_ids']['views']['tree']['arch'] = etree.tostring(doc1, encoding='unicode')
                result['arch'] = etree.tostring(doc, encoding='unicode')
        return result

    mt_new_feature = fields.Boolean(string="Enable(?)", default=False,
                                        help="According to cameron changes need to handle payroll line m show/hide.")
    state = fields.Selection(selection=[('1', _("past")),
                                            ('2', _("present")),
                                            ('3', _("future"))],
                             compute='_compute_state_payroll',
                                 store=True,
                                 default='2')
    retirement_budget_amount_mt_new_feature = fields.Float(
        string="Retirement Amount", compute='_compute_retirement_total_mt_new_feature', track_visibility="onchange")
    company_id = fields.Many2one('res.company',string='Company',default=lambda self:self.env.user.company_id.id)
    
    @api.depends('payroll_line_m_ids.next_year_gratuity_m')
    def _compute_retirement_total_mt_new_feature(self):
        for rec in self:
            planned_amount_100 = 0
            planned_amount = 0
            record = rec.env['budgetextension.budget'].search(
                    [('id', '=', rec.retirement_budget_id.id),('no_overwrite','=',False)])
            
            for line in rec.payroll_line_m_ids:
                planned_amount_100 = planned_amount_100 + line.next_year_gratuity_m
            if record and rec.mt_new_feature:
                planned_amount = planned_amount_100 * record.ccm_budget_percent / 100
                record.write({
                    'planned_amount_100': planned_amount_100,
                    'planned_amount': planned_amount})
                record.planned_amount_100 = planned_amount_100
            rec.retirement_budget_amount_mt_new_feature = planned_amount_100

    @api.depends('to_date')
    def _compute_state_payroll(self):
        for record in self:
            if record.from_date and record.to_date:
                end_date = datetime.strptime(str(record.to_date),
                                            DEFAULT_SERVER_DATE_FORMAT)
                fd = self.env.user.company_id.fiscalyear_last_day
                fm = self.env.user.company_id.fiscalyear_last_month
                now = datetime.now()
                e_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (now.year, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                )
                if str(now.date()) > str(e_fiscal_date.date()):
                    e_fiscal_date = datetime.strptime(
                        "%s-%s-%s" % (now.year + 1, fm, fd),
                        DEFAULT_SERVER_DATE_FORMAT
                    )
                s_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                ) + timedelta(days=1)
                if str(end_date.date()) < str(s_fiscal_date.date()):
                    record.state = '1'
                elif str(end_date.date()) > str(e_fiscal_date.date()):
                    record.state = '3'
                else:
                    record.state = '2'

    def _cron_compute_state_payroll(self):
        res = self.search([('state', '!=', '1')])
        for record in res:
            record._compute_state_payroll()



class CapitalBudgetTemplate(models.Model):
    _inherit = "capital.budget.template"

    @api.model
    def fields_view_get(self, view_id=None, view_type='form', toolbar=False,
                        submenu=False):
        result = super(CapitalBudgetTemplate, self).fields_view_get(view_id,
                                                                     view_type,
                                                                     toolbar=toolbar,
                                                                     submenu=submenu)
        doc = etree.XML(result['arch'])
        
        ref_view_id = self.env.ref('mt_isy.isy_capital_budget_template_view_tree')
        last_year_ref_view_id = self.env.ref('mt_isy.isy_capital_budget_template_view_tree_all')
        future_year_ref_view_id = self.env.ref('mt_isy.isy_capital_budget_template_view_tree_future')
        form_ref_view_id = self.env.ref('mt_isy.isy_capital_budget_template_view_form')
        if view_type == 'tree' and self._module == 'mt_isy':
            if view_id == ref_view_id.id:
                val = self._get_year_from_to('current')
                #planned amount
                planned_amount_neg_ref = doc.xpath(
                    "//field[@name='planned_amount_neg']")
                planned_amount_neg_ref[0].set(
                    "string", val['current_year'] + " - \n Budget(C)")
                #last year planned amount
                last_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_year_planned_amount_neg']")
                last_year_planned_amount_neg_ref[0].set(
                    "string", val['last_year'] + " - \n Budget(B)")
                #last 2 years planned amount
                last_2_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_2_year_planned_amount_neg']")
                last_2_year_planned_amount_neg_ref[0].set(
                    "string", val['last_2_year'] + " - \n Budget(A)")

                result['arch'] = etree.tostring(doc, encoding='unicode')
            elif view_id == last_year_ref_view_id.id:
                val = self._get_year_from_to('last')

                #planned amount
                planned_amount_neg_ref = doc.xpath(
                    "//field[@name='planned_amount_neg']")
                planned_amount_neg_ref[0].set(
                    "string", val['current_year'] + " - \n Budget(C)")
                #last year planned amount
                last_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_year_planned_amount_neg']")
                last_year_planned_amount_neg_ref[0].set(
                    "string", val['last_year'] + " - \n Budget(B)")
                #last 2 years planned amount
                last_2_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_2_year_planned_amount_neg']")
                last_2_year_planned_amount_neg_ref[0].set(
                    "string", val['last_2_year'] + " - \n Budget(A)")

                result['arch'] = etree.tostring(doc, encoding='unicode')
            elif view_id == future_year_ref_view_id.id:
                val = self._get_year_from_to('future')

                #planned amount
                planned_amount_neg_ref = doc.xpath(
                    "//field[@name='planned_amount_neg']")
                planned_amount_neg_ref[0].set(
                    "string", val['current_year'] + " - \n Budget(C)")
                #last year planned amount
                last_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_year_planned_amount_neg']")
                last_year_planned_amount_neg_ref[0].set(
                    "string", val['last_year'] + " - \n Budget(B)")
                #last 2 years planned amount
                last_2_year_planned_amount_neg_ref = doc.xpath(
                    "//field[@name='last_2_year_planned_amount_neg']")
                last_2_year_planned_amount_neg_ref[0].set(
                    "string", val['last_2_year'] + " - \n Budget(A)")

                result['arch'] = etree.tostring(doc, encoding='unicode')
        
        elif view_type == 'form' and self._module == 'mt_isy':
            if view_id == form_ref_view_id.id:
                # if not 'params' in self._context.keys():
                #     return result
                # if not 'id' in self._context.get('params').keys():
                #     return result
                if not 'params' in self._context.keys() or not 'id' in self._context.get('params',{}).keys():
                    if self._context.get('state','0')=='3': # Future
                        val = self._get_year_from_to('future')
                    elif self._context.get('state','0')=='2': # Current
                        val = self._get_year_from_to('current')
                    else: # Current
                        val = self._get_year_from_to('last')
                    past_year = val['last_year']
                    current_year = val['current_year']
                    past_2_year = val['last_2_year']
                else:
                    obj_budget = self.env['capital.budget.template'].search(
                        [('id', '=', self._context.get('params')['id'] or False)])
                    if obj_budget:
                        past_year = str(obj_budget.from_date.year - 1)[2::] + "/" + str(obj_budget.to_date.year - 1)[2::]
                        current_year = str(obj_budget.from_date.year)[2::] + "/" + str(obj_budget.to_date.year)[2::]
                        past_2_year = str(obj_budget.from_date.year - 2)[2::] + "/" + str(obj_budget.to_date.year - 2)[2::]
                    else:
                        past_year = "Past Year Budget (B)"
                        current_year = "Current Year Budget (C)"
                        past_2_year = "Future Year Budget (A)"
                
                current_year_budget = current_year + "- Budget(C)"
                past_year_budget = past_year + "- Budget(B)"
                past_2_year_budget = past_2_year + "- Budget(A)"

                current_year_ref = doc.xpath("//field[@name='planned_amount']")
                current_year_ref[0].set("string", current_year_budget+" [85%]")
                current_year_ref = doc.xpath("//field[@name='planned_amount_100']")
                current_year_ref[0].set("string", current_year_budget+" [100%]")

                past_year_ref = doc.xpath("//field[@name='last_year_planned_amount']")
                past_year_ref[0].set("string", past_year_budget)

                past_2_year_ref = doc.xpath(
                    "//field[@name='last_2_year_planned_amount']")
                past_2_year_ref[0].set("string", past_2_year_budget)

                result['arch'] = etree.tostring(doc, encoding='unicode')

        return result

    def _get_year_from_to(self, val):
        fd = self.env.user.company_id.fiscalyear_last_day
        fm = self.env.user.company_id.fiscalyear_last_month
        now = datetime.now()
        result = {}
        e_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (now.year, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            )
        if now.date() > e_fiscal_date.date():
            e_fiscal_date = datetime.strptime(
                "%s-%s-%s" % (now.year + 1, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            ) + timedelta(days=1)
        s_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        ) + timedelta(days=1)
        if val == 'current':            
            result = {
                'current_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_2_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],

            }
        elif val == 'last':
            result = {
                'current_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],
                'last_2_year': str(s_fiscal_date.date().year-3)[2::] + "/" + str(e_fiscal_date.date().year-3)[2::],

            }
        elif val == 'future':
            result = {
                'current_year': str(s_fiscal_date.date().year+1)[2::] + "/" + str(e_fiscal_date.date().year+1)[2::],
                'last_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_2_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],

            }
        elif val == 'date_from_to':
            result = {
                'date_from': s_fiscal_date.date(),
                'date_to': e_fiscal_date.date(),
            }
        return result

    state = fields.Selection(selection=[('1', _("past")),
                                        ('2', _("present")),
                                        ('3', _("future"))],
                             compute='_compute_state_capital',
                             store=True,
                             default='2')
    company_id = fields.Many2one('res.company',string='Company',default=lambda self:self.env.user.company_id.id)
    planned_amount = fields.Float(
        string="Allowed Amount", compute='', track_visibility="onchange",store=True)
    planned_amount_100 = fields.Float(
        string="Planned Amount (100%)", compute='_compute_total', track_visibility="onchange")

    @api.onchange('planned_amount_100')
    def change_planned_amount(self):
        for rec in self:
            rec.planned_amount = rec.planned_amount_100*85/100

    @api.depends('planned_amount', 'last_year_planned_amount', 'last_2_year_planned_amount')
    def compute_negative(self):
        for rec in self:
            if rec.type_id.is_expense:
                rec.planned_amount_neg = -(rec.planned_amount_100)
                rec.last_year_planned_amount_neg = -(rec.last_year_planned_amount)
                rec.last_2_year_planned_amount_neg = -(rec.last_2_year_planned_amount)
            else:
                rec.planned_amount_neg = rec.planned_amount_100
                rec.last_year_planned_amount_neg = rec.last_year_planned_amount
                rec.last_2_year_planned_amount_neg = rec.last_2_year_planned_amount

    @api.depends('line_total', 'enrollment_fee', 'contingency_percentage', 'contingency_amount', 'current_year_reserve', 'application_fee')
    def _compute_total(self):
        calc = 0
        total = 0
        for rec in self:
            if rec.is_enrollment:
                calc = (rec.line_total * rec.enrollment_fee) * \
                    rec.contingency_percentage / 100
                rec.contingency_amount = calc
                total = (rec.line_total * rec.enrollment_fee) + \
                    rec.contingency_amount
            elif rec.is_reserve:
                calc = rec.current_year_reserve * rec.contingency_percentage / 100
                rec.contingency_amount = calc
                total = rec.current_year_reserve + rec.contingency_amount
            else:
                if rec.is_application:
                    calc = (rec.line_total * rec.application_fee) * \
                        rec.contingency_percentage / 100
                    rec.contingency_amount = calc
                    total = (rec.line_total * rec.application_fee) + \
                        rec.contingency_amount
                else:
                    calc = (rec.line_total) * \
                        rec.contingency_percentage / 100
                    rec.contingency_amount = calc
                    total = rec.line_total + rec.contingency_amount
            rec.planned_amount_100 = total
            # rec.planned_amount = total*85/100


    @api.depends('to_date')
    def _compute_state_capital(self):
        for record in self:
            if record.from_date and record.to_date:
                end_date = datetime.strptime(str(record.to_date),
                                             DEFAULT_SERVER_DATE_FORMAT)
                fd = self.env.user.company_id.fiscalyear_last_day
                fm = self.env.user.company_id.fiscalyear_last_month
                now = datetime.now()
                e_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (now.year, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                )
                if str(now.date()) > str(e_fiscal_date.date()):
                    #2022-06-30
                    e_fiscal_date = datetime.strptime(
                        "%s-%s-%s" % (now.year + 1, fm, fd),
                        DEFAULT_SERVER_DATE_FORMAT
                    )

                s_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                ) + timedelta(days=1)
                if str(end_date.date()) < str(s_fiscal_date.date()):
                    record.state = '1'
                elif str(end_date.date()) > str(e_fiscal_date.date()):
                    record.state = '3'
                else:
                    record.state = '2'

    def _cron_compute_state_capital(self):
        res = self.search([('state', '!=', '1')])
        for record in res:
            record._compute_state_capital()


class RevenueBudgetYgn(models.Model):
    _inherit = "revenue.budget.ygn"
    _rec_name = "budget_id"
    
    from_date = fields.Date(string="From Date", store=True)
    to_date = fields.Date(string="To Date", store=True)
    state = fields.Selection(selection=[('1', _("past")),
                                        ('2', _("present")),
                                        ('3', _("future"))],
                             compute='_compute_state_revenue',
                             store=True,
                             default='2')
    company_id = fields.Many2one('res.company',string='Company',default=lambda self:self.env.user.company_id.id)
    surcharge_amount = fields.Float('Surcharge')

    @api.model
    def fields_view_get(self, view_id=None, view_type='tree', toolbar=False,
                        submenu=False):
        result = super(RevenueBudgetYgn, self).fields_view_get(view_id,
                                                                     view_type,
                                                                     toolbar=toolbar,
                                                                     submenu=submenu)
        doc = etree.XML(result['arch'])
        if view_type == 'tree' and self._module == 'mt_isy':
            #current view
            ref_view_id = self.env.ref(
                'mt_isy.isy_revenue_budget_ygn_view_tree')
           
            future_year_ref_view_id = self.env.ref(
                'mt_isy.isy_revenue_budget_ygn_view_tree_future')
            if view_id == ref_view_id.id:
                val = self._get_year_from_to('current')
                #current year
                current_year_student_ref = doc.xpath(
                    "//field[@name='current_year_student']")
                current_year_student_ref[0].set(
                    "string", val['last_year'] + " - \n Student")
                
                current_year_fee_ref = doc.xpath(
                    "//field[@name='current_year_fee']")
                current_year_fee_ref[0].set(
                    "string", val['last_year'] + " - \n Fee")
                
                current_year_total_ref = doc.xpath(
                    "//field[@name='current_year_total']")
                current_year_total_ref[0].set(
                    "string", val['last_year'] + " - \n Total")

                next_year_student_ref = doc.xpath(
                    "//field[@name='next_year_student']")
                next_year_student_ref[0].set(
                    "string", val['current_year'] + " - \n Student")
                
                next_year_fee_ref = doc.xpath(
                    "//field[@name='next_year_fee']")
                next_year_fee_ref[0].set(
                    "string", val['current_year'] + " - \n Fee")
                
                next_year_total_ref = doc.xpath(
                    "//field[@name='next_year_total']")
                next_year_total_ref[0].set(
                    "string", val['current_year'] + " - \n Total")
               
                result['arch'] = etree.tostring(doc, encoding='unicode')

            elif view_id == future_year_ref_view_id.id:
                val = self._get_year_from_to('future')
                #current year
                current_year_student_ref = doc.xpath(
                    "//field[@name='current_year_student']")
                current_year_student_ref[0].set(
                    "string", val['last_year'] + " - \n Student")

                current_year_fee_ref = doc.xpath(
                    "//field[@name='current_year_fee']")
                current_year_fee_ref[0].set(
                    "string", val['last_year'] + " - \n Fee")

                current_year_total_ref = doc.xpath(
                    "//field[@name='current_year_total']")
                current_year_total_ref[0].set(
                    "string", val['last_year'] + " - \n Total")

                next_year_student_ref = doc.xpath(
                    "//field[@name='next_year_student']")
                next_year_student_ref[0].set(
                    "string", val['current_year'] + " - \n Student")

                next_year_fee_ref = doc.xpath(
                    "//field[@name='next_year_fee']")
                next_year_fee_ref[0].set(
                    "string", val['current_year'] + " - \n Fee")

                next_year_total_ref = doc.xpath(
                    "//field[@name='next_year_total']")
                next_year_total_ref[0].set(
                    "string", val['current_year'] + " - \n Total")
                result['arch'] = etree.tostring(doc, encoding='unicode')

        return result

    def _get_year_from_to(self, val):
        fd = self.env.user.company_id.fiscalyear_last_day
        fm = self.env.user.company_id.fiscalyear_last_month
        now = datetime.now()
        result = {}
        e_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (now.year, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        )
        if now.date() > e_fiscal_date.date():
            e_fiscal_date = datetime.strptime(
                "%s-%s-%s" % (now.year + 1, fm, fd),
                DEFAULT_SERVER_DATE_FORMAT
            ) + timedelta(days=1)
        s_fiscal_date = datetime.strptime(
            "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
            DEFAULT_SERVER_DATE_FORMAT
        ) + timedelta(days=1)
        if val == 'current':
            result = {
                'current_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_2_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],

            }
        elif val == 'last':
            result = {
                'current_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],
                'last_year': str(s_fiscal_date.date().year-2)[2::] + "/" + str(e_fiscal_date.date().year-2)[2::],
                'last_2_year': str(s_fiscal_date.date().year-3)[2::] + "/" + str(e_fiscal_date.date().year-3)[2::],

            }
        elif val == 'future':
            result = {
                'current_year': str(s_fiscal_date.date().year+1)[2::] + "/" + str(e_fiscal_date.date().year+1)[2::],
                'last_year': str(s_fiscal_date.date().year)[2::] + "/" + str(e_fiscal_date.date().year)[2::],
                'last_2_year': str(s_fiscal_date.date().year-1)[2::] + "/" + str(e_fiscal_date.date().year-1)[2::],

            }
        elif val == 'date_from_to':
            result = {
                'date_from': s_fiscal_date.date(),
                'date_to': e_fiscal_date.date(),
            }
        return result

    @api.depends('to_date')
    def _compute_state_revenue(self):
        for record in self:
            if record.from_date and record.to_date:
                end_date = datetime.strptime(str(record.to_date),
                                             DEFAULT_SERVER_DATE_FORMAT)
                fd = self.env.user.company_id.fiscalyear_last_day
                fm = self.env.user.company_id.fiscalyear_last_month
                now = datetime.now()
                e_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (now.year, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                )
                if str(now.date()) > str(e_fiscal_date.date()):
                    e_fiscal_date = datetime.strptime(
                        "%s-%s-%s" % (now.year + 1, fm, fd),
                        DEFAULT_SERVER_DATE_FORMAT
                    )
                s_fiscal_date = datetime.strptime(
                    "%s-%s-%s" % (e_fiscal_date.year - 1, fm, fd),
                    DEFAULT_SERVER_DATE_FORMAT
                ) + timedelta(days=1)
                if str(end_date.date()) < str(s_fiscal_date.date()):
                    record.state = '1'
                elif str(end_date.date()) > str(e_fiscal_date.date()):
                    record.state = '3'
                else:
                    record.state = '2'

    def _cron_compute_state_revenue(self):
        res = self.search([('state', '!=', '1')])
        for record in res:
            record._compute_state_revenue()

    @api.depends('next_year_student', 'next_year_fee','surcharge_amount')
    def _compute_next_total(self):
        total = 0
        for rec in self:
            total = (rec.next_year_fee+rec.surcharge_amount) * rec.next_year_student
            record = rec.env['budgetextension.budget'].search(
                [('id', '=', rec.budget_id.id),('no_overwrite','=',False)])
            if record:
                planned_amount = total * record.ccm_budget_percent / 100
                record.update({
                    'planned_amount_100': total,
                    'planned_amount': planned_amount})
                # record.write({'planned_amount_100': rec.next_year_total})
            rec.next_year_total = total


class RentalBudget(models.Model):
    _inherit = "rental.budget"
    
    company_id = fields.Many2one('res.company',string='Company',default=lambda self:self.env.user.company_id.id)

