# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import tools
from odoo import api, fields, models


class EmployeePayableReceivableReport(models.Model):
    _name = "employee.payable.receivable.report"
    _description = "Employee Payable Receivable Analysis Report"
    _auto = False
    _rec_name = 'request_date'
    _order = 'request_date desc'

    name = fields.Char('Reference', readonly=True)
    request_date = fields.Datetime('Requested Date', readonly=True)
    employee_id = fields.Many2one('hr.employee', 'Employee', readonly=True)
    #requested_amount = fields.Float('Requested Amount', readonly=True)
    #clear_settle_amount = fields.Float('Clear/Settle Amount', readonly=True)
    adv_exp_type = fields.Selection([('advance','Receivable'),('expense','Payable')], readonly=True)
    balance = fields.Float('Balance', readonly=True)
    currency_id = fields.Many2one('res.currency', readonly=True)

    def init(self):
        # self._table = sale_report
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute(""" CREATE VIEW employee_payable_receivable_report AS (
            select A.id as id,
                A.name as name,
                A.request_date as request_date,
                A.employee_id as employee_id,
                A.currency_id as currency_id,
                A.adv_exp_type as adv_exp_type,
                case 
                    when A.adv_exp_type = 'advance' then sum(A.requested_amount) - sum(A.clear_settle_amount)
                    else SUM(A.requested_amount - A.clear_settle_amount)
                end as balance  
                    From ( 
                        SELECT
                            eae.id as id,
                            eae.request_date as request_date,
                            eae.name as name,
                            eae.employee_id as employee_id,
                            resc.id as currency_id,
                            eae.total_amount_expense as requested_amount,
                            case 
                                when eae.adv_exp_type = 'advance' then 'Receivable'
                                when eae.adv_exp_type = 'expense' then 'Payable'
                            end as adv_exp_type,
                            case 
                                when eae.adv_exp_type = 'advance' and aecl.id is not null then aecl.quantity*aecl.unit_amount 
                                when eae.adv_exp_type = 'advance' and aecl.id is null then round(0)
                                when eae.adv_exp_type = 'expense' and eae.state='payable' then 0
                            end as clear_settle_amount
                        FROM
                            employee_advance_expense as eae
                        LEFT JOIN
                            advance_expense_clearance_line as aecl ON aecl.advance_id = eae.id
                        INNER JOIN
                            res_currency as resc on resc.id = eae.currency_id
                        where 
                            eae.state in ('done','partial','payable')
                        GROUP BY
                            eae.name,
                            eae.employee_id,
                            eae.adv_exp_type,eae.id,
                            resc.id,
                            aecl.id
                    )A
                GROUP BY
                    A.id,
                    A.name,
                    A.employee_id,
                    A.currency_id,
                    A.adv_exp_type,
                    A.request_date
        )""")