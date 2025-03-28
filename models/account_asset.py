# -*- coding: utf-8 -*-
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare, float_is_zero
from datetime import date, datetime, time

from odoo.osv import expression

try:
    import xlsxwriter
except ImportError:
    _logger.debug('Can not import xlsxwriter`.')

import logging
_logger = logging.getLogger(__name__)


class AccountFiscalYear(models.Model):
    _name = 'account.fiscal.year'

    name = fields.Char('Name')
    date_from = fields.Date('From Date')
    date_to = fields.Date('To Date')
    company_id = fields.Many2one('res.company','Company')
    active = fields.Boolean('Active')
    ccm_budget = fields.Boolean('CCM Budget')


class AccountAssetAsset(models.Model):
    _inherit = 'account.asset'

    posted_count = fields.Integer('Posted Count',compute="compute_posted_count")

    # @api.depends('depreciation_line_ids.move_check')
    def compute_posted_count(self):
        for rec in self:
            # rec.posted_count = len(rec.depreciation_line_ids.filtered(lambda x: x.move_check==True).ids)
            rec.posted_count = len(rec.depreciation_move_ids.filtered(lambda x: x.state=='posted').ids)
            

class AccountAccount(models.Model):
    _inherit = 'account.account'

    group_id = fields.Many2one('account.group', store=True, readonly=False,
                               help="Account prefixes can determine account groups.")
    extra_group_id = fields.Many2many('account.group.extra',string="Extra Account")
    savings_for_education = fields.Boolean('College Education Saving?')
    no_budget = fields.Boolean('No Budget',default=False)
    x_studio_account_type = fields.Selection(
        string="Account Type", related="account_type")

    def _adapt_parent_account_group(self):
        pass

    def _adapt_accounts_for_account_groups(self, account_ids=None):
        """Ensure consistency between accounts and account groups.

        Find and set the most specific group matching the code of the account.
        The most specific is the one with the longest prefixes and with the starting
        prefix being smaller than the account code and the ending prefix being greater.
        """
        pass
        
    @api.depends('code')
    def _compute_account_group(self):
        pass

    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, name_get_uid=None, order=None):
        args = args or []
        domain = []
        if name:
            domain = ['&','|', ('code', '=ilike', name.split(' ')[0] + '%'), ('name', operator, name),('company_id','in',self.env.companies.ids)]
            if operator in expression.NEGATIVE_TERM_OPERATORS:
                domain = ['&', '!'] + domain[1:]
        
        account_ids = self._search(expression.AND([domain, args]), limit=limit, access_rights_uid=name_get_uid,order=order)
        return account_ids


class AccountGroup(models.Model):
    _inherit = 'account.group'

    def _adapt_parent_account_group(self):
        pass

    def _adapt_accounts_for_account_groups(self, account_ids=None):
        """Ensure consistency between accounts and account groups.

        Find and set the most specific group matching the code of the account.
        The most specific is the one with the longest prefixes and with the starting
        prefix being smaller than the account code and the ending prefix being greater.
        """
        pass

class AccountGroupExtra(models.Model):
    _name = 'account.group.extra'

    name = fields.Char('Name')
    company_id = fields.Many2one('res.company',default=lambda x: x.env.user.company_id.id)