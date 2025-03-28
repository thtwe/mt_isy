# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    @api.depends('journal_id', 'payment_type', 'payment_method_line_id')
    def _compute_outstanding_account_id(self):
        for pay in self:
            if pay.payment_type == 'inbound':
                pay.outstanding_account_id = (pay.journal_id.default_account_id or pay.journal_id.company_id.account_journal_payment_debit_account_id)
            elif pay.payment_type == 'outbound':
                pay.outstanding_account_id = (pay.journal_id.default_account_id or pay.journal_id.company_id.account_journal_payment_credit_account_id)
            else:
                pay.outstanding_account_id = False

    # state = fields.Selection(selection_add=[('confirmed','Confirmed'),('approved','Approved')])
    # state_internal = fields.Selection(related='state')

    # def action_confirm(self):
    #     for rec in self:
    #         first_approver = self.env['ir.config_parameter'].sudo().get_param(
    #             'mt_isy.payment_first_approver', False)
    #         if self.env.user.id!=int(first_approver):
    #             raise UserError("You can not confirm.")
    #         rec.state = 'confirmed'
    
    # def action_approve(self):
    #     for rec in self:
    #         second_approver = self.env['ir.config_parameter'].sudo().get_param(
    #             'mt_isy.payment_second_approver', False)
    #         if self.env.user.id!=int(second_approver):
    #             raise UserError("You can not approve.")
    #         rec.state = 'approved'

    # def post(self):
    #     self.state='draft'
    #     return super(AccountPayment, self).post()
