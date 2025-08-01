# -*- coding: utf-8 -*-

from odoo import api, fields, models

class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    public = fields.Boolean('Is public document', default=True)
