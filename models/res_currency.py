# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import date, datetime, timedelta
from dateutil.relativedelta import relativedelta

import calendar

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

class RescurrencyRate(models.Model):
    _name = "res.currency.rate"
    _inherit = "res.currency.rate"

    def create_monthly_rate(self):
        mmk_cur_id = self.env.ref('base.MMK').id
        latest_rate = self.search([('currency_id', '=', mmk_cur_id)], order='name desc', limit=1)

        if latest_rate.name <= fields.Date.today():
            next_day = latest_rate.name + timedelta(days=1)
            last_day_of_month = calendar.monthrange(next_day.year, next_day.month)[1]
            last_day = next_day + timedelta(days=last_day_of_month - next_day.day)
            rate = latest_rate.rate
            while next_day <= last_day:
                name = next_day.strftime('%Y-%m-%d')
                self.create({
                    'name': name,
                    'currency_id': mmk_cur_id,
                    'rate': rate
                })
                next_day += timedelta(days=1)
