# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError

class IsyApproval(models.Model):
    _name = 'isy.approval'
    _descirption = 'Approval'
    _inherit = 'mail.thread'

    name = fields.Char(string="Sequence")
    subject = fields.Char(string="Request For")
    body = fields.Text(string="Description")
    isy_approval_category_id = fields.Many2one('isy.approval.category', string="Request Category")
    first_approver = fields.Many2one('res.users', string="First Approval Person", store=True)
    date_first_approval = fields.Date(string="First Approval Date")
    second_approver = fields.Many2one('res.users', string="Second Approval Person", store=True)
    date_second_approval = fields.Date(string="Second Approval Date")
    state = fields.Selection([('draft', 'Draft'), ('waitingforapproval', 'WaitingforApproval'), ('toapprove', 'ToApprove'), ('rejected', 'Rejected'), ('approved', 'Approved')], default='draft', track_visibility='onchange')

    @api.onchange('isy_approval_category_id')
    def change_category_id(self):
        self.first_approver = self.isy_approval_category_id.first_approver.id
        self.second_approver = self.isy_approval_category_id.second_approver.id

    def approve_request(self):
        if self.env.user.id != self.first_approver.id:
            raise ValidationError(_("You are not allow to approve for this record."))
        else:
            self.date_first_approval = str(fields.Datetime.now().date())
            if self.second_approver:
                self.state = 'toapprove'
            else:
                self.state = 'approved'

    def second_approve_request(self):
        if self.env.user.id != self.second_approver.id:
            raise ValidationError(_("You are not allow to approve for this record."))
        else:
            self.date_second_approval = str(fields.Datetime.now().date())
            self.state = 'approved'

    def reject_request(self):
        if self.env.user.id != self.first_approver.id:
            raise ValidationError(_("You are not allow to approve for this record."))
        elif self.env.user.id != self.second_approver.id:
            raise ValidationError(_("You are not allow to approve for this record."))
        else:
            self.state = 'rejected'

    @api.model
    def create(self, values):
        values['state'] = 'waitingforapproval'
        res = super(IsyApproval, self).create(values)
        return res

class IsyApprovalCategory(models.Model):
    _name = 'isy.approval.category'

    name = fields.Char(string="Category Name")
    first_approver = fields.Many2one('res.users', string="First Approval Person")
    second_approver = fields.Many2one('res.users', string="Second Approval Person")
    active = fields.Boolean(string="Active(?)", default=True)
