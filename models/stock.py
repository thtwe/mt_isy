# -*- coding: utf-8 -*-

from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from odoo.tools import float_compare
import base64
import xlrd
import logging

_logger = logging.getLogger(__name__)

ISY_TYPE = [('out', 'Out'), ('in', 'In')]

class InternalStockTransfer(models.Model):
    _name = 'internal.stock.transfer'
    _description = 'Internal Stock Transfer'

    name = fields.Char(string="Name", readonly=True,  required=True, copy=False, default='New')
    date_transfer = fields.Datetime(string="Transfer Date", help="DateTime of stock transfer")
    date_schedule = fields.Datetime(string="Schedule Date", default=fields.Datetime.now(), help="Schedule date of stock transfer/It can same with datetime or cannot same if the stock transfer need to schedule")
    assigned_person = fields.Many2one('hr.employee', string="Assigned Person")
    ist_type = fields.Selection(ISY_TYPE, string="Type")
    source_location = fields.Many2one('stock.location', string="From")
    destination_location = fields.Many2one('stock.location', string="To")
    remark = fields.Text(string="Remark")
    ist_details = fields.One2many('internal.stock.transfer.details', 'ist_id', string="Internal Stock Transfer Details")
    barcode_scanned = fields.Char(string="BarcodeScan")
    msg_validation = fields.Char(string="Warning")
    state = fields.Selection([('draft', 'Draft'),('firstapproval','WaitingForFirstApproval'),('secondapproval','WaitingForSecondApproval'),('reserved', 'Reserved'), ('done', 'Done'),('cancelled','Cancelled')], string="State", default="draft")
    require_assign_person = fields.Boolean(sring="Require Assign Person(?)")
    picking_type_id = fields.Many2one('stock.picking.type', string="Operation Type", compute="_get_picking_type_id", store=True)
    picking_id = fields.Many2one('stock.picking')
    #to handle grant funded transfer
    is_grant_funded_transfer = fields.Boolean(string="Grant Funded Transfer", default=False)
    product_id = fields.Many2one('product.product', string='Product')
    #to handle disposal  approval
    first_approval = fields.Many2one('res.users', string="First Approval")
    second_approval = fields.Many2one('res.users', string="Second Approval")
    assigned_type = fields.Selection([('employee','Employee'),('student','Student')], string="Assigned Type")
    assigned_student = fields.Many2one('res.partner',domain=[('student_number','!=',False)])
    # donated_to = fields.Char(string="Donated To")
    donated_to = fields.Many2one('isy.donated.to',string="Donate To")
    is_donation = fields.Boolean(string="Donation Location(?)", default=False)
    purchase_id = fields.Many2one("purchase.order", string="Purchase Order")
    inventory_category = fields.Selection(
        [('asset', 'Asset'), ('non-asset', 'Non-Asset')], string="Inventory Category")
    assets_responsible_person = fields.Many2one('res.users', string="Asset Responsible Person")
    assets_included = fields.Boolean('res.users', default=False, compute='_check_assets_included')

    @api.depends('ist_details')
    def _check_assets_included(self):
        for rec in self:
            assets_included = False
            for rec_ist_details in rec.ist_details:
                if rec_ist_details.inventory_category == 'asset':
                    assets_included = True
                    break
                else:
                    assets_included = False
            rec.assets_included = assets_included
                

    def first_approve(self):
        if self.first_approval:
            if self.env.user.id != self.first_approval.id:
                raise ValidationError(_("You are not allowed to approve this."))
        self.state = 'secondapproval'

    def cancel_approve(self):
        self.state = 'cancelled'

    def add_grant_funded_item(self):
        msg_validation = False
        null_tmp = False
        if self.barcode_scanned and self. product_id:
            if self.product_id.tracking != 'serial':
                raise ValidationError(_("Product tracking type is not serial. \n Please change product tracking type to 'Serial'."))
            obj_isy_stock_report = self.env['isy.stock.report'].search([('serial_number','=', self.barcode_scanned)])
            obj_ist_details = self.env['internal.stock.transfer.details'].search(
                [('serial_number', '=', self.barcode_scanned)])
            rest = obj_ist_details.filtered(lambda r: r.ist_id.state in (
                'draft', 'reserved') and r.ist_id != self.id).sorted(key=lambda r: r.id)
            result_list = [res.ist_id.name for res in rest]
            if obj_isy_stock_report:
                msg_validation = "Barcode number already exists in stock report."
                self.with_context(nocheck=True).update(
                    {'barcode_scanned': null_tmp, 'product_id': null_tmp, 'purchase_id': null_tmp, 'inventory_category': null_tmp, 'msg_validation': msg_validation})
            elif self.name in result_list:
                msg_validation = "Serial Number is already added into transfer details"
                self.with_context(nocheck=True).update(
                    {'barcode_scanned': null_tmp, 'product_id': null_tmp, 'purchase_id': null_tmp, 'inventory_category': null_tmp, 'msg_validation': msg_validation})
            elif result_list:
                msg_validation = "Serial Number " + self.barcode_scanned + \
                    " already exists in progress records " + \
                    str(result_list) + "."
                self.with_context(nocheck=True).update(
                    {'barcode_scanned': null_tmp, 'product_id': null_tmp, 'purchase_id': null_tmp, 'inventory_category': null_tmp, 'msg_validation': msg_validation})
            else:
                lst_std_details = [(0, 0,
                                    {
                                        'serial_number': self.barcode_scanned,
                                        'product_id': self.product_id.id,
                                        'qty': 1,
                                        'purchase_id': self.purchase_id.id,
                                        'inventory_category': self.inventory_category,

                                    },
                                    )]
                self.with_context(nocheck=True).update({'barcode_scanned': null_tmp, 'product_id': null_tmp, 'purchase_id': null_tmp, 'inventory_category': null_tmp, 'ist_details': lst_std_details, 'msg_validation': ''})
        else:
            msg_validation = "Please fill barcode and product before you click ADD button."
            self.with_context(nocheck=True).update({'barcode_scanned': null_tmp, 'product_id': null_tmp, 'purchase_id': null_tmp, 'inventory_category': null_tmp, 'msg_validation': msg_validation})

    @api.depends('source_location', 'destination_location')
    def _get_picking_type_id(self):
        for rec in self:
            rec.picking_type_id = self.env['stock.picking.type'].sudo().search([('default_location_src_id', '=', rec.source_location.id), ('default_location_dest_id', '=', rec.destination_location.id)])
            if not rec.picking_type_id and rec.source_location and rec.source_location.usage=='internal' and rec.destination_location and rec.destination_location.usage=='internal':
                sequence_code = rec.env['ir.sequence'].sudo().search([('code','=','isy.internal.stock.transfer')]).id
                if not sequence_code:
                    raise ValidationError(_("Please ask administrator to create isy.internal.stock.transfer sequence code."))
                
                vals = {
                    'code': 'internal',
                    'sequence_code': 'internal',
                    'default_location_src_id': rec.source_location.id,
                    'default_location_dest_id': rec.destination_location.id,
                    'sequence_id': sequence_code,
                    'show_reserved': 1,
                    'use_existing_lots': 1,
                    'use_create_lots': False,
                    'name': rec.source_location.name + " To " + rec.destination_location.name,
                }
                result = self.env['stock.picking.type'].sudo().create(vals)
                rec.picking_type_id = result.id
            elif not rec.picking_type_id and rec.source_location and rec.source_location.usage=='internal' and rec.destination_location and rec.destination_location.usage in ('customer','inventory'):
                sequence_code = rec.env['ir.sequence'].sudo().search([('code','=','isy.internal.stock.transfer')]).id
                if not sequence_code:
                    raise ValidationError(_("Please ask administrator to create isy.internal.stock.transfer sequence code."))
                
                vals = {
                    'code': 'outgoing',
                    'sequence_code': 'outgoing',
                    'default_location_src_id': rec.source_location.id,
                    'default_location_dest_id': rec.destination_location.id,
                    'sequence_id': sequence_code,
                    'show_reserved': 1,
                    'use_existing_lots': 1,
                    'use_create_lots': False,
                    'name': rec.source_location.name + " To " + rec.destination_location.name,
                }
                result = self.env['stock.picking.type'].sudo().create(vals)
                rec.picking_type_id = result.id
            elif not rec.picking_type_id and rec.source_location and rec.source_location.usage=='supplier' and rec.destination_location and rec.destination_location.usage=='internal':
                sequence_code = rec.env['ir.sequence'].sudo().search([('code','=','isy.internal.stock.transfer')]).id
                if not sequence_code:
                    raise ValidationError(_("Please ask administrator to create isy.internal.stock.transfer sequence code."))
                
                vals = {
                    'code': 'incoming',
                    'sequence_code': 'incoming',
                    'default_location_src_id': rec.source_location.id,
                    'default_location_dest_id': rec.destination_location.id,
                    'sequence_id': sequence_code,
                    'show_reserved': 1,
                    'use_existing_lots': False,
                    'use_create_lots': 1,
                    'name': rec.source_location.name + " To " + rec.destination_location.name,
                }
                result = self.env['stock.picking.type'].sudo().create(vals)
                rec.picking_type_id = result.id
            elif not rec.picking_type_id:
                rec.picking_type_id = False


    @api.onchange('destination_location')
    def check_assign_person_require(self):
        if self.destination_location:
            self.require_assign_person = self.destination_location.require_assign_person
            self.is_donation = self.destination_location.is_donation or self.destination_location.name=='Donate'
            self.donated_to = False
            if not self.require_assign_person:
                self.assigned_type = False
                self.assigned_person = False
                self.assigned_student = False
            if self.destination_location.usage in ['inventory','customer']:
                self.first_approval = self.env['hr.employee'].search([('user_id','=',self.env.user.id)]).parent_id.user_id.id or False
                self.second_approval = self.destination_location.second_approval.id or False
            else:
                self.first_approval = False
                self.second_approval = False


    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('isy.internal.stock.transfer') or 'New'
        if vals.get('first_approval') and vals.get('second_approval'):
            vals['state'] = 'firstapproval'
        obj_source_location = self.env['stock.location'].search([('id','=',vals.get('source_location'))])
        obj_destination_location = self.env['stock.location'].search([('id','=',vals.get('destination_location'))])
        if obj_source_location.require_assign_person == True and obj_destination_location.require_assign_person == True:
            raise ValidationError(_("Personal location to personal location transfer is not allow!"))
        if not vals.get('ist_details') and not vals.get('is_grant_funded_transfer'):
            raise ValidationError(_("Please add stock items."))
        if vals.get('ist_details'):
            for val in vals.get('ist_details'):
                serial_number = val[2]['serial_number']
                obj_ist_details = self.env['internal.stock.transfer.details'].search([('serial_number', '=', serial_number)])
                rest = obj_ist_details.filtered(lambda r: r.ist_id.state in ('draft','reserved')).sorted(key=lambda r: r.id)
                result_list = [res.ist_id.name for res in rest]
                if result_list:
                    raise ValidationError(_("Serial Number "+ serial_number + " already exists in progress records "+ str(result_list) +"."))                

        result = super(InternalStockTransfer, self).create(vals)
        if result.destination_location.require_assign_person == True and result.assigned_type=='employee' and result.assigned_person and not result.assigned_person.sudo().address_id:
            raise ValidationError(_("%s doesn't have contact information. Please contact to the odoo admin."%(result.assigned_person.sudo().name)))
        return result

    def write(self, values):
        """Override default Odoo write function and extend."""
        res = super(InternalStockTransfer, self).write(values)
        if self.msg_validation:
            self.msg_validation = ''
        if not self.ist_details and not self._context.get('nocheck') and ( not self.barcode_scanned or not values.get('barcode_scanned')):
            raise ValidationError(_("Please add stock items."))
        return res

    #     if values.get('ist_details'):
    #         for val in values.get('ist_details'):
    #             if val[2] != False:
    #                 serial_number = val[2]['serial_number']
    #                 obj_ist_details = self.env['internal.stock.transfer.details'].search([('serial_number', '=', serial_number)])
    #                 rest = obj_ist_details.filtered(lambda r: r.ist_id.state in ('draft','reserved') and r.ist_id.id != self.id).sorted(key=lambda r: r.id)
    #                 result_list = [res.ist_id.name for res in rest]
    #                 if result_list:
    #                     raise ValidationError(_("Serial Number "+ serial_number + " already exists in progress records "+ str(result_list) +"."))
    #             else:
    #                 if not self.ist_details:
    #                     raise ValidationError(_("Please add stock items."))            
    #             #     else:
    #             #         if len(self.ist_details) == len(values.get('ist_details')):
    #             #             raise ValidationError(_("Please add stock items."))
    #     # elif not self.ist_details and values.get('state') and values.get('state') != 'cancelled':
    #     #     raise ValidationError(_("Please add stock items."))
    #     # elif not self.ist_details and not values.get('state'):
    #     #     raise ValidationError(_("Please add stock items."))
    #     return super(InternalStockTransfer, self).write(values)

    def reserved_stock(self):
        if self.first_approval and self.second_approval and self.state != 'reserved':
            if self.env.user.id != self.second_approval.id:
                raise ValidationError(_("You are not allowed to approve this."))
        if not self.picking_type_id:
            self._get_picking_type_id()
            if not self.picking_type_id:
                raise ValidationError(_("Please ask administrator to create new picking type by providing your source location and destination location."))
        if not self.env.context.get('again'):
            picking = {
                'location_id': self.source_location.id,
                'location_dest_id': self.destination_location.id,
                'scheduled_date': self.date_schedule,
                'origin': self.name,
                'picking_type_id': self.picking_type_id.id,

            }
            picking_details = []
            qty = 0
            pid_serial = []
            for istd in self.ist_details:
                picking_details.append(
                    (0, 0, {
                        'product_id': istd.product_id.id,
                        'name': istd.product_id.sudo().name,
                        'product_uom_qty': istd.qty,
                        'product_uom': istd.product_id.sudo().uom_id.id,
                        'location_id': istd.ist_id.source_location.id,
                        'location_dest_id': istd.ist_id.destination_location.id,
                        'date': istd.ist_id.date_schedule,
                        'picking_type_id': istd.ist_id.sudo().picking_type_id.id,
                        'company_id': self.env.user.company_id.id,
                    })
                )
                pid_serial.append({'product_id': istd.product_id.id, 'serial_number': istd.serial_number})

            picking.update({'move_ids_without_package': picking_details})
            obj_stock_picking = self.env['stock.picking']
            obj_stock_picking_id = obj_stock_picking.sudo().create(picking)
            

            owner_id = False
            if self.assigned_type == 'employee':
                owner_id = self.assigned_person.sudo().address_id.id
            elif self.assigned_type == 'student':
                owner_id = self.assigned_student.sudo().id
            obj_stock_picking_id.write({'owner_id': owner_id or False})
            #obj_stock_picking_id.action_assign_owner()
            if obj_stock_picking_id.state == 'draft':
                obj_stock_picking_id.action_confirm()
            if obj_stock_picking_id.state == 'confirmed':
                obj_stock_picking_id.action_assign()
            
            for sml_details in obj_stock_picking_id.move_line_ids:
                for ps in pid_serial:
                    if ps['product_id'] == sml_details.product_id.id:
                        if self.is_grant_funded_transfer == True:
                            lot_id = self.env['stock.lot'].sudo().create({
                                'name': ps['serial_number'],
                                'product_id': ps['product_id'],
                                'company_id':self.env.user.company_id.id,
                            }                          
                            )
                        else:
                            lot_id = self.env['stock.lot'].sudo().search([('name', '=', ps['serial_number'])])
                        sml_details.write(
                            {
                                'lot_id': lot_id.id,
                                'qty_done': 1,
                                'owner_id': owner_id,

                            }
                        )
                        pid_serial.remove(ps)
                        break

            self.state = "reserved"
            self.picking_id = obj_stock_picking_id.id
        elif self.env.context.get('again'):
            pid_serial = []
            owner_id = False
            if self.assigned_type == 'employee':
                owner_id = self.assigned_person.sudo().address_id.id
            elif self.assigned_type == 'student':
                owner_id = self.assigned_student.sudo().id

            for istd in self.ist_details:
                pid_serial.append({'product_id': istd.product_id.id, 'serial_number': istd.serial_number})
            self.picking_id.do_unreserve()
            self.picking_id.action_assign()
            for sml_details in self.picking_id.move_line_ids:
                for ps in pid_serial:
                    if ps['product_id'] == sml_details.product_id.id:
                        if self.is_grant_funded_transfer == True:
                            lot_id = self.env['stock.lot'].sudo().create({
                                'name': ps['serial_number'],
                                'product_id': ps['product_id'],
                                'company_id':self.env.user.company_id.id,
                            }                          
                            )
                        else:
                            lot_id = self.env['stock.lot'].sudo().search([('name', '=', ps['serial_number'])])
                        sml_details.write(
                            {
                                'lot_id': lot_id.id,
                                'qty_done': 1,
                                'owner_id': owner_id,


                            }
                        )
                        pid_serial.remove(ps)
                        break

    def transferred_stock(self):
        if self.source_location.require_assign_person == True:
            self.with_context(again=True).sudo().reserved_stock()
            stock_objs = self.env['isy.stock.report'].search([('serial_number','in',self.ist_details.mapped('serial_number') or [])])
            owners = stock_objs.mapped('assigned_to')
            owner_lst = {}
            for stock in stock_objs:
                owner = stock.assigned_to
                product = stock.product_id.name+' ['+stock.serial_number+']'
                if not owner_lst.get(owner.id):
                    owner_lst.update({owner.id:[product]})
                else:
                    owner_lst[owner.id].append(product)
        self.picking_id.sudo().button_validate()
        self.date_transfer = fields.Datetime.now()
        
        if self.assets_included:
            resp_user_id = self.env['ir.config_parameter'].sudo().get_param(
                'mt_isy.assets_responsible_person_inventory_transfer', '178')
            self.assets_responsible_person = int(resp_user_id)
            template = self.env.ref('mt_isy.assets_reminder_inventory_opening')
            self.env['mail.template'].browse(template.id).send_mail(self.id)

        if self.source_location.require_assign_person == True:
            template = self.env.ref(
                    'mt_isy.inventory_item_checkout')
            serial_number_objs = self.ist_details.mapped('serial_number') or []
            for owner in owners:
                context = {}
                products = self.env['isy.stock.report'].search([('assigned_to','=',owner.id),('serial_number','not in',serial_number_objs)])
                checkout_items = owner_lst.get(owner.id) or []
                context.update({
                    'owner': owner,
                    'checkout_items': checkout_items,
                    'products': products,
                    })
                template.with_context(**context).send_mail(self.id)
        if self.destination_location.require_assign_person == True:
            template = self.env.ref(
                    'mt_isy.inventory_item_assigned')
            if template:
                template.send_mail(self.id)
        self.state = "done"

    @api.onchange('ist_type')
    def change_ist_type(self):
        if self.ist_type and self.ist_type == 'out':
            self.source_location = self.env.user.default_location_id.id
            self.destination_location = False
        elif self.ist_type and self.ist_type == 'in':
            self.destination_location = self.env.user.default_location_id.id
            self.source_location = False

    @api.onchange('source_location')
    def clear_ist_details(self):
        if not self.source_location:
            self.ist_details.unlink()
        if self.source_location.grant_funded_location or self.source_location.usage=='supplier':
            self.is_grant_funded_transfer = True
        else:
            self.is_grant_funded_transfer = False

    @api.onchange("barcode_scanned")
    def add_move_items(self):
        if self.barcode_scanned and self.is_grant_funded_transfer == False:
            if not self.source_location:
                self.source_location = self.env['isy.stock.report'].search([('serial_number', '=', self.barcode_scanned)]).location_id.id
            if self.source_location:
                msg_validation = False
                barcode = self.barcode_scanned
                qty = 1
                lot_id = self.env['stock.lot'].sudo().search([('name', '=', barcode)])
                product_id = lot_id.product_id.id
                obj_stock_report = self.env['isy.stock.report'].search([('serial_number','=', barcode)])
                quant_check = self.env['stock.quant'].sudo().search([('lot_id', '=', lot_id.id), ('location_id', '=', self.source_location.id), ('location_id.usage', '=', 'internal')])
                check_aval = sum(quant_check.mapped('quantity'))
                if (not quant_check or check_aval == float(0)) and lot_id:
                    msg_validation = "Your serial number doesn't exist in your source location!"
                else:
                    disable_qty = True
                    if not lot_id:
                        product_id = self.env['product.product'].sudo().search([('barcode', '=', barcode)])
                        if not product_id:
                            msg_validation = "There has no serial number/ product with the barcode number!"
                        elif product_id and product_id.tracking == 'serial':
                            msg_validation = ' '
                        disable_qty = False

                if not msg_validation:
                    lst_std_details = [(0, 0,
                                        {
                                            'serial_number': barcode if disable_qty else '',
                                            'product_id': product_id,
                                            'qty': qty,
                                            'disable_qty': disable_qty,
                                            'assigned_department': obj_stock_report.assigned_department.id,
                                        },
                                        )]
                    self.update({'barcode_scanned': '', 'ist_details': lst_std_details, 'msg_validation': ''})
                else:
                    self.update({'barcode_scanned': '', 'msg_validation': msg_validation})

            else:
                msg_validation = "Please choose source location!"
                self.update({'barcode_scanned': '', 'msg_validation': msg_validation})


class InternalStockTransferDetails(models.Model):
    _name = 'internal.stock.transfer.details'
    _description = 'Internal Stock Transfer Details'

    ist_id = fields.Many2one('internal.stock.transfer', string="Reference No.")
    serial_number = fields.Char(string="Serial Number(Barcode)", help="It can either serial number or product barcode")
    product_id = fields.Many2one('product.product', string='Product')
    qty = fields.Float(string="Qty", default=1, store=True)
    disable_qty = fields.Boolean(string="Disable Qty")
    date_schedule_return = fields.Date(string='Schedule Return Date', help="It can track for when this item will return")
    source_location = fields.Many2one(related='ist_id.source_location', string="From")
    destination_location = fields.Many2one(related='ist_id.destination_location', string="To")
    date_transfer = fields.Datetime(related='ist_id.date_transfer', string="Date Transfer")
    assigned_person = fields.Many2one(related='ist_id.assigned_person', string="Assign Person")
    assigned_student = fields.Many2one(related='ist_id.assigned_student', string="Assign Student")
    assigned_department = fields.Many2one('hr.department', string="Assigned Department")
    purchase_id = fields.Many2one("purchase.order", string="Purchase Order")
    inventory_category = fields.Selection(
        [('asset', 'Asset'), ('non-asset', 'Non-Asset')], string="Inventory Category")

    @api.model
    def _automatic_reminder_for_schedule_return(self):
        for rec in self.search([('date_schedule_return', '!=', False)]):
            no_of_days = abs(
                (fields.Date.today() - rec.date_schedule_return).days)
            days_end = self.env['ir.config_parameter'].get_param(
                'mt_isy.days_end_reminder', '3')
            if no_of_days <= int(days_end):
                if rec.ist_id.assigned_type == 'employee':
                    template = self.env.ref(
                        'mt_isy.automatic_reminder_for_schedule_return_employee')
                elif rec.ist_id.assigned_type == 'student':
                    template = self.env.ref(
                        'mt_isy.automatic_reminder_for_schedule_return_student')
                if template:
                    self.env['mail.template'].browse(template.id).send_mail(rec.id)

    @api.constrains('serial_number')
    def _validate_serial_number(self):
        for rec in self:
            val = self.search(
                [('serial_number', '=', rec.serial_number), ('ist_id', '=', rec.ist_id.id)])
            if len(val) > 1:
                raise ValidationError(_("You cannot add duplicate entry to transfer details."))

    def show_stock_report_by_serial_number(self):
        res_id = self.env['isy.stock.report'].search([('serial_number', '=',self.serial_number)])
        form_id = self.env.ref(
            'mt_isy.isy_stock_report_form_show_details', False)
        return {
            'name': 'Stock Report Information',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'isy.stock.report',
            'res_id': res_id.id,
            'views': [(form_id.id, 'form')],
            'target': 'new',
            'domain': [],
            'context': {},
        }

class ResUsers(models.Model):
    _inherit = 'res.users'

    default_location_id = fields.Many2one('stock.location', string="Default Location", domain=[('usage', '=', 'internal')])

class StockLocation(models.Model):
    _inherit = 'stock.location'

    require_assign_person = fields.Boolean(string="Require Assign Person(?)")
    grant_funded_location = fields.Boolean(string="Is Grant Funded Location(?)")
    second_approval = fields.Many2one('res.users', string="Disposal Second Approval")
    is_donation = fields.Boolean(string="Donation Location(?)", default=False)
    is_it = fields.Boolean(string="IT Internal Location?")

class ISYDonatedTo(models.Model):
    _name = "isy.donated.to"

    name = fields.Char('Name')

class IsyStockReport(models.Model):
    _name = 'isy.stock.report'

    name = fields.Char(string="Product Description")
    product_id = fields.Many2one("product.product",string="Product Description")
    serial_number = fields.Char(string="Barcode Number")
    location_id = fields.Many2one("stock.location", string="Location")
    inventory_category = fields.Selection([('asset', 'Asset'), ('non-asset', 'Non-Asset')], string="Inventory Category")
    product_category = fields.Many2one("product.category", string="Product Type")
    purchase_id = fields.Many2one("purchase.order", string="Purchase Order")
    purchase_date = fields.Date(string="Purchase Date")
    acquisition_cost = fields.Float(string="Acquisition Cost (USD)")
    assigned_type = fields.Selection([('employee','Employee'),('student','Student')], string="Assigned Type")
    assigned_to = fields.Many2one("res.partner", string="Assigned Person")    
    note = fields.Text(string="Note")
    manufacturer = fields.Char(string="Manufacturer")
    model_number = fields.Char(string="Model")
    it_serial_number = fields.Char(string="Serial Number")
    grant_funded_item = fields.Boolean(string="Grant Funded Item")
    assigned_department = fields.Many2one('hr.department', string="Assigned Department")
    user_email = fields.Char('User reserved?')
    contact_reserved = fields.Many2one('res.partner',string='Reserved By',compute='compute_user_reserved',store=True)

    @api.depends('user_email')
    def compute_user_reserved(self):
        for rec in self:
            if rec.user_email:
                rec.contact_reserved = self.env['res.partner'].sudo().search([('email','=',rec.user_email)],limit=1).id
            else:
                rec.contact_reserved = False


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def button_validate(self):
        result = super(StockPicking, self).button_validate()
        isr_list = []
        if self.picking_type_id.code == 'incoming':
            for val in self.move_line_ids:
                obj_po = self.env['purchase.order'].search([('name', '=', val.picking_id.origin)]) or False
                if obj_po:
                    acq_cost = obj_po.order_line.search([('product_id', '=', val.product_id.id)])[0].price_unit or False
                    if obj_po.currency_id.name == 'USD':
                        usd_acq_cost = acq_cost
                    else:
                        usd_acq_cost = obj_po.currency_id.compute(acq_cost, obj_po.company_id.currency_id)
                    if obj_po.is_asset == True and val.product_id.type == 'product':
                        asset_value = self.env['ir.config_parameter'].get_param('isy_assets_definition', '')
                        if not asset_value:
                            raise ValidationError(_("Please ask administrator to define assets value definition."))
                        # if usd_acq_cost > float(asset_value) and not val.product_id.asset_category_id:
                        #     raise UserError(_("Please fill assets category for assets items."))
                        if usd_acq_cost >= float(asset_value):
                            inventory_category = 'asset'
                        else:
                            inventory_category = 'non-asset'
                    else:
                        inventory_category = 'non-asset'

                else:
                    acq_cost, usd_acq_cost = False, False
                    inventory_category = 'non-asset'
                #handle opening stock from isy inventory transfer by passing purchase information
                #passing purchase information from po still exists in else statement
                obj_ist = self.env['internal.stock.transfer'].search([('picking_id','=',val.picking_id.id)])
                if obj_ist:
                    obj_ist_details = self.env['internal.stock.transfer.details'].search([('serial_number','=', val.lot_id.name),('ist_id','=',obj_ist.id)])
                    if not obj_po:
                        inventory_category = obj_ist_details.inventory_category
                    if obj_ist_details and obj_ist_details.purchase_id:
                        purchase_id = obj_ist_details.purchase_id.id
                        purchase_date = obj_ist_details.purchase_id.date_order.date()
                    else:
                        purchase_id = False
                        purchase_date = False 
                        if not obj_po:
                            inventory_category = False
                else:
                    purchase_id = obj_po and obj_po.id or False
                    purchase_date = obj_po and obj_po.date_order.date() or val.picking_id.date_done.date()
                    if not obj_po:
                        inventory_category = False

                isr_list.append(
                    {
                        'name': val.product_id.name,
                        'product_id': val.product_id.id,
                        'serial_number': val.lot_id.name,
                        'location_id': val.location_dest_id.id,
                        'inventory_category': inventory_category,
                        'product_category': val.product_id.categ_id.id,
                        'purchase_id': purchase_id,
                        'purchase_date': purchase_date,
                        'acquisition_cost': usd_acq_cost or False,
                        'assigned_to': val.owner_id.id,
                        'assigned_type': obj_ist.assigned_type,
                        'manufacturer': val.manufacturer,
                        'model_number': val.model,
                        'it_serial_number': val.it_serial_number,
                        'assigned_department': val.assigned_department.id,
                        'grant_funded_item': True if val.location_id.grant_funded_location == True else False,
                        'note': obj_ist.remark or ''
                    }
                )
                assets_related_obj_po_ids = self.env['account.asset'].search([('name', 'ilike', str(val.picking_id.origin) + '%'), ('name', 'ilike', '%[%s]')])
                for arop in assets_related_obj_po_ids:
                    new_name = arop.name.replace('%s', val.lot_id.name)
                    self.env.cr.execute("""update account_asset_asset set name='""" + str(new_name) + """' where id=""" + str(arop.id))
                    self.env.cr.commit()
                    break
            self.env['isy.stock.report'].create(isr_list)
        else:
            for val in self.move_line_ids:
                #owner_id = self.env['hr.employee'].search([('address_id', '=', val.owner_id.id), ('address_id', '!=', False)]).id
                obj_isr = self.env['isy.stock.report'].search([('serial_number', '=', val.lot_id.name)])
                pass_note = ''
                if not obj_isr.note:
                    pass_note = str(self.env['internal.stock.transfer'].search([('picking_id', '=', val.picking_id.id)]).remark) or ''
                else:
                    remark = self.env['internal.stock.transfer'].search([('picking_id', '=', val.picking_id.id)]).remark or ''
                    if remark:
                        pass_note = str(obj_isr.note or '') + " | " + str(remark)
                    else:
                        pass_note = str(obj_isr.note or '')
                if val.location_dest_id.require_assign_person == True:
                    isr_val = {
                        'location_id': val.location_dest_id.id, 
                        'assigned_to': val.owner_id.id,
                        'assigned_type': self.env['internal.stock.transfer'].search([('picking_id','=',val.picking_id.id)]).assigned_type, 
                        'product_category': val.product_id.categ_id.id,
                        'note': pass_note}
                else:
                    isr_val = {
                        'location_id': val.location_dest_id.id, 
                        'assigned_to': False, 
                        'assigned_type': False, 
                        'product_category': val.product_id.categ_id.id,
                        'note': pass_note}
                if val.product_id.categ_id.is_it==True or val.product_id.is_it==True:
                    if val.location_dest_id.is_it==True: 
                        isr_val.update({'user_email':False})
                    elif val.location_id.is_it==True:
                        if obj_isr.user_email == False:
                            raise UserError("This product didn't reserved yet. Please make it reserved on IT Inventory Ordering System.")
                obj_isr.write(isr_val)
                obj_schedule_return_lists = self.env['internal.stock.transfer.details'].search([('serial_number', '=', val.lot_id.name), ('date_schedule_return', '!=', False)])
                ist_type = self.env['internal.stock.transfer'].search([('picking_id', '=', val.picking_id.id)]).ist_type
                if obj_schedule_return_lists and ist_type == 'in':
                    obj_schedule_return_lists.write({'date_schedule_return': False})
        return result


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    manufacturer = fields.Char(string="Manufacturer")
    model = fields.Char(string="Model")
    it_serial_number = fields.Char(string="Serial Number")
    assigned_department = fields.Many2one('hr.department', string="Assigned Department")

class AccountMove(models.Model):
    _inherit = 'account.move'

    # def asset_create(self):
    #     if self.asset_category_id and self.product_id.type != 'service':
    #         picking_id = self.env['stock.picking'].search([('origin', '=', self.purchase_id.name)])
    #         if picking_id and picking_id.state != 'done':
    #             for ml in picking_id.move_line_ids:
    #                 if ml.product_id.id == self.product_id.id:
    #                     vals = {
    #                         'name': self.name + ' - ' + '[%s]',
    #                         'code': self.invoice_id.number or False,
    #                         'category_id': self.asset_category_id.id,
    #                         'value': self.price_subtotal_signed / self.quantity,
    #                         'partner_id': self.invoice_id.partner_id.id,
    #                         'company_id': self.invoice_id.company_id.id,
    #                         'currency_id': self.invoice_id.company_currency_id.id,
    #                         'date': self.invoice_id.date_invoice,
    #                         'invoice_id': self.invoice_id.id,
    #                     }
    #                     changed_vals = self.env['account.asset'].onchange_category_id_values(vals['category_id'])
    #                     vals.update(changed_vals['value'])
    #                     asset = self.env['account.asset'].create(vals)
    #                     if self.asset_category_id.open_asset:
    #                         asset.validate()
    #         elif picking_id and picking_id.state == 'done':
    #             for ml in picking_id.move_line_ids:
    #                 if ml.product_id.id == self.product_id.id:
    #                     vals = {
    #                         'name': self.name + ' - [' + ml.lot_name + ']',
    #                         'code': self.invoice_id.number or False,
    #                         'category_id': self.asset_category_id.id,
    #                         'value': self.price_subtotal_signed / self.quantity,
    #                         'partner_id': self.invoice_id.partner_id.id,
    #                         'company_id': self.invoice_id.company_id.id,
    #                         'currency_id': self.invoice_id.company_currency_id.id,
    #                         'date': self.invoice_id.date_invoice,
    #                         'invoice_id': self.invoice_id.id,
    #                     }
    #                     changed_vals = self.env['account.asset'].onchange_category_id_values(vals['category_id'])
    #                     vals.update(changed_vals['value'])
    #                     asset = self.env['account.asset'].create(vals)
    #                     if self.asset_category_id.open_asset:
    #                         asset.validate()
    #         else:
    #             raise UserError('There has no related stock picking for this invoice related PO. Please receipt stock first!')
    #     elif self.asset_category_id and self.product_id.type == 'service':
    #         vals = {
    #             'name': self.name,
    #             'code': self.invoice_id.number or False,
    #             'category_id': self.asset_category_id.id,
    #             'value': self.price_subtotal_signed,
    #             'partner_id': self.invoice_id.partner_id.id,
    #             'company_id': self.invoice_id.company_id.id,
    #             'currency_id': self.invoice_id.company_currency_id.id,
    #             'date': self.invoice_id.date_invoice,
    #             'invoice_id': self.invoice_id.id,
    #         }
    #         changed_vals = self.env['account.asset'].onchange_category_id_values(vals['category_id'])
    #         vals.update(changed_vals['value'])
    #         asset = self.env['account.asset'].create(vals)
    #         if self.asset_category_id.open_asset:
    #             asset.validate()
    #     return True

    def _auto_create_asset(self):
        # not used by ISY. create asset manually.
        create_list = []
        invoice_list = []
        auto_validate = []
        for move in self:
            if not move.is_invoice():
                continue

            # for move_line in move.line_ids.filtered(lambda line: not (move.move_type in ('out_invoice', 'out_refund') and line.account_id.user_type_id.internal_group == 'asset')):
            for move_line in move.line_ids.filtered(lambda line: line.asset_model_id and line.move_id.x_studio_is_asset_1 and not (move.move_type in ('out_invoice', 'out_refund') and line.account_id.internal_group == 'asset')):
                # if move_line.account_id.user_type_id.internal_group != 'asset':
                #     raise UserError('%s is not Asset Type. Cannot create asset entry.'%(move_line.account_id.display_name))
                
                # ISY
                if (
                    move_line.account_id
                    # and (move_line.account_id.can_create_asset)
                    # and move_line.account_id.create_asset != "no"
                    and not move.reversed_entry_id
                    and not (move_line.currency_id or move.currency_id).is_zero(move_line.price_total)
                    # and not move_line.asset_ids
                    # and not move_line.tax_line_id
                    and move_line.price_total > 0
                ):
                    if not move_line.name:
                        raise UserError(_('Journal Items of {account} should have a label in order to generate an asset').format(account=move_line.account_id.display_name))
                    if move_line.account_id.multiple_assets_per_line:
                        # decimal quantities are not supported, quantities are rounded to the lower int
                        units_quantity = max(1, int(move_line.quantity))
                    else:
                        units_quantity = 1
                    name = ''
                    if move_line.product_id.type != 'service':
                        picking_id = self.env['stock.picking'].search([('origin', '=', move_line.move_id.purchase_id.name)])
                        for ml in picking_id.move_line_ids:
                            if ml.product_id.id == move_line.product_id.id:
                                if picking_id and picking_id.state != 'done':
                                    name = move_line.product_id.name + ' - ' + '[%s]'
                                else:
                                    name = move_line.product_id.name + ' - [' + (ml.lot_name or '') + ']'

                                vals = {
                                    'name': name,
                                    'company_id': move_line.company_id.id,
                                    'currency_id': move_line.company_currency_id.id,
                                    'account_analytic_id': move_line.analytic_account_id.id,
                                    'analytic_tag_ids': [(6, False, move_line.analytic_tag_ids.ids)],
                                    'original_move_line_ids': [(6, False, move_line.ids)],
                                    'state': 'draft',
                                }

                                model_id = move_line.asset_model_id or move_line.account_id.asset_model
                                if model_id:
                                    vals.update({
                                        'model_id': model_id.id,
                                    })
                                auto_validate.extend([move_line.account_id.create_asset == 'validate'] * units_quantity)
                                invoice_list.extend([move] * units_quantity)
                                for i in range(1, units_quantity + 1):
                                    if units_quantity > 1:
                                        vals['name'] = move_line.name + _(" (%s of %s)", i, units_quantity)
                                    create_list.extend([vals.copy()])
                    elif move_line.product_id.type=='service':
                        vals = {
                            'name': move_line.name,
                            'company_id': move_line.company_id.id,
                            'currency_id': move_line.company_currency_id.id,
                            'account_analytic_id': move_line.analytic_account_id.id,
                            'analytic_tag_ids': [(6, False, move_line.analytic_tag_ids.ids)],
                            'original_move_line_ids': [(6, False, move_line.ids)],
                            'state': 'draft',
                        }
                        model_id = move_line.account_id.asset_model
                        if model_id:
                            vals.update({
                                'model_id': model_id.id,
                            })
                        auto_validate.extend([move_line.account_id.create_asset == 'validate'] * units_quantity)
                        invoice_list.extend([move] * units_quantity)
                        for i in range(1, units_quantity + 1):
                            if units_quantity > 1:
                                vals['name'] = move_line.name + _(" (%s of %s)", i, units_quantity)
                            create_list.extend([vals.copy()])
                # source code
                elif (
                    move_line.account_id
                    and (move_line.account_id.can_create_asset)
                    and move_line.account_id.create_asset != "no"
                    and not move.reversed_entry_id
                    and not (move_line.currency_id or move.currency_id).is_zero(move_line.price_total)
                    and not move_line.asset_ids
                    and not move_line.tax_line_id
                    and move_line.price_total > 0
                ):
                    if not move_line.name:
                        raise UserError(_('Journal Items of {account} should have a label in order to generate an asset').format(account=move_line.account_id.display_name))
                    if move_line.account_id.multiple_assets_per_line:
                        # decimal quantities are not supported, quantities are rounded to the lower int
                        units_quantity = max(1, int(move_line.quantity))
                    else:
                        units_quantity = 1
                    vals = {
                        'name': move_line.name,
                        'company_id': move_line.company_id.id,
                        'currency_id': move_line.company_currency_id.id,
                        'account_analytic_id': move_line.analytic_account_id.id,
                        'analytic_tag_ids': [(6, False, move_line.analytic_tag_ids.ids)],
                        'original_move_line_ids': [(6, False, move_line.ids)],
                        'state': 'draft',
                    }
                    model_id = move_line.account_id.asset_model
                    if model_id:
                        vals.update({
                            'model_id': model_id.id,
                        })
                    auto_validate.extend([move_line.account_id.create_asset == 'validate'] * units_quantity)
                    invoice_list.extend([move] * units_quantity)
                    for i in range(1, units_quantity + 1):
                        if units_quantity > 1:
                            vals['name'] = move_line.name + _(" (%s of %s)", i, units_quantity)
                        create_list.extend([vals.copy()])

        assets = self.env['account.asset'].create(create_list)
        for asset, vals, invoice, validate in zip(assets, create_list, invoice_list, auto_validate):
            if 'model_id' in vals:
                asset._onchange_model_id()
                if validate:
                    asset.validate()
            if invoice:
                asset_name = {
                    'purchase': _('Asset'),
                    'sale': _('Deferred revenue'),
                    'expense': _('Deferred expense'),
                }[asset.asset_type]
                msg = _('%s created from invoice') % (asset_name)
                msg += ': <a href=# data-oe-model=account.move data-oe-id=%d>%s</a>' % (invoice.id, invoice.name)
                asset.message_post(body=msg)
        # assets.compute_depreciation_board()
        return assets

# class AccountInvoice(models.Model):
#     _inherit = 'account.invoice'
#
#     def action_invoice_open(self):
#         # lots of duplicate calls to action_invoice_open, so we remove those already open
#         to_open_invoices = self.filtered(lambda inv: inv.state != 'open')
#         if to_open_invoices.filtered(lambda inv: not inv.partner_id):
#             raise UserError(_("The field Vendor is required, please complete it to validate the Vendor Bill."))
#         if to_open_invoices.filtered(lambda inv: inv.state != 'draft'):
#             raise UserError(_("Invoice must be in draft state in order to validate it."))
#         if to_open_invoices.filtered(lambda inv: float_compare(inv.amount_total, 0.0, precision_rounding=inv.currency_id.rounding) == -1):
#             raise UserError(_("You cannot validate an invoice with a negative total amount. You should create a credit note instead."))
#         if to_open_invoices.filtered(lambda inv: not inv.account_id):
#             raise UserError(_('No account was found to create the invoice, be sure you have installed a chart of account.'))
#         to_open_invoices.action_date_assign()
#         to_open_invoices.action_move_create()
#         for invl in self.invoice_line_ids:
#             acq_cost = invl.price_unit
#             if invl.currency_id.name == 'USD':
#                 usd_acq_cost = acq_cost
#             else:
#                 usd_acq_cost = invl.currency_id._convert(acq_cost, invl.company_id.currency_id, invl.company_id,  fields.Datetime().now().date())
#             if invl.purchase_id.is_asset == True and invl.product_id.type == 'product':
#                 asset_value = self.env['ir.config_parameter'].get_param('isy_assets_definition', '')
#                 if not asset_value:
#                     raise ValidationError(_("Please ask administrator to define assets value definition."))
#                 if usd_acq_cost >= float(asset_value) and not invl.asset_category_id:
#                     raise UserError(_("Please fill assets category for assets items."))
#
#         return to_open_invoices.invoice_validate()

class StocKQuant(models.Model):
    _inherit = 'stock.quant'

    @api.constrains('quantity')
    def check_quantity(self):
        return True

class StockAuditing(models.Model):
    _name = 'stock.auditing'
    _description = 'Stock Audition Process'

    def _get_default_employee(self):
        employee_id = self.env['hr.employee'].search(
            [('user_id', '=', self.env.user.id)]).id
        return employee_id

    def _get_default_first_approval(self):
        approval_id = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.audit_first_approval', 0)
        return int(approval_id)
    
    def _get_default_second_approval(self):
        approval_id = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.audit_second_approval', 0)
        return int(approval_id)

    @api.depends('closing_stock_details')
    def _get_closing_stock_count(self):
        for rec in self:
            rec.closing_stock_count = rec.closing_stock_details.search_count(
                [('stock_auditing_closing_id','=',rec.id)])

    @api.depends('different_stock_details')
    def _get_isy_stocks(self):
        for rec in self:
            rec.isy_stock_report_count = rec.different_stock_details.search_count(
                [('stock_auditing_different_id', '=', rec.id)]) + rec.closing_stock_count

    @api.depends('closing_stock_details', 'different_stock_details')
    def _get_missing_stocks(self):
        for rec in self:
            if rec.closing_stock_count and rec.isy_stock_report_count:
                rec.missing_stock_count = rec.isy_stock_report_count - rec.closing_stock_count
            else:
                rec.missing_stock_count = 0

    name = fields.Char(string="Ref No.", size=128, readonly="1", default="New")
    audit_date = fields.Date(string="Stock Audit Date", default=fields.Datetime.now().date())
    fiscal_year = fields.Many2one('account.fiscal.year', string="Fiscal Year")
    employee_id = fields.Many2one('hr.employee', string="Responsible Person", default=_get_default_employee)
    closing_stock_count = fields.Float(string="Closing Stock Count", default=0, compute="_get_closing_stock_count", store=1, readonly=1)
    isy_stock_report_count = fields.Float(
        string="ISY Stock Report Count", compute="_get_isy_stocks", store=1, readonly=1)
    missing_stock_count = fields.Float(
        string="Missing Stock Count", default=0, compute="_get_missing_stocks", store=1, readonly=1)
    closing_stock_attachment = fields.Binary(string="Closing Stock Attachment", attachment=True, required=True, filters='.xls',)
    closing_stock_attachment_label = fields.Char(string="Attachment Name")
    state = fields.Selection([('draft', 'Draft'), ('firstapproval', 'WaitingForFirstApproval'), ('secondapproval', 'WaitingForSecondApproval'),
                             ('done', 'Done'), ('cancelled', 'Cancelled')], string="State", default='draft')
    closing_stock_details = fields.One2many('stock.auditing.closing.stock', 'stock_auditing_closing_id', string="Closing Stock Details")
    different_stock_details = fields.One2many('stock.auditing.different.stock', 'stock_auditing_different_id', string="Different Stock Details")
    first_approval = fields.Many2one('res.users', string="First Approval", default=_get_default_first_approval, readonly=1, store=1)
    second_approval = fields.Many2one('res.users', string="Second Approval", default=_get_default_second_approval, readonly=1, store=1)
    remark = fields.Text(string="Remark")

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code(
                'stock.auditing') or 'New'
        result = super(StockAuditing, self).create(vals)
        return result

    def generate_closign_stock_by_upload_attachment(self):
        _logger.info(
            "================load closing stock attachment data started=================")
        #1. Get Closing Audit Stock Lists
        #2. Get the barcode number which are not exists in system or duplicate inside system
        #3. Get the barcode number which are exists in system but not exist in closing stock lists.

        #Get external location only
        external_location_ids = self.env['stock.location'].search(
            [('second_approval', '!=', False), ('usage', 'in', ['inventory', 'customer'])]).ids
        for rec in self:

            if rec.closing_stock_details:
                rec.closing_stock_details.unlink()
            if rec.different_stock_details:
                rec.different_stock_details.unlink()
            closing_stock_details_list = [] 
            closing_barcode_list = []
            remark = "There has issues in Barcode Number. \n It cannot be found in system or duplicate. \n Please see below: \n"

            decoded_data = base64.decodestring(rec.closing_stock_attachment)
            wb = xlrd.open_workbook(file_contents=decoded_data)
            sh = wb.sheet_by_index(0)
            for rownum in range(sh.nrows):
                if sh.ncols > 1:
                    raise ValidationError(_("Your uploaded excel format is wrong.\nIt should be only one column with barcode number information."))
                if rownum != 0:
                    for val in sh.row_values(rownum):
                        result = self.env['isy.stock.report'].search([('serial_number','=',val)])
                        #check closing barcode number are existing in disposal location or not.
                        if result and len(result) == 1:
                            if result.location_id.id in external_location_ids:
                                raise ValidationError(
                                    _("Barcode Number " + val + " is in disposal location.\n Please check your barcode number."))
                            closing_stock_details_list.append((0, 0, {
                                'name': result.serial_number,
                                'product_category': result.product_category.id,
                                'location_id': result.location_id.id,
                                'product_id': result.product_id.id,
                                'assigned_type': result.assigned_type,
                                'inventory_category': result.inventory_category,
                                'assigned_to': result.assigned_to.id,
                                'assigned_department': result.assigned_department.id,
                            }))
                        else:
                            remark += str(val) + " , \n"
                            _logger.warning("======Not Found In ISY Report ====>" + str(val) )
                        closing_barcode_list.append(str(val))
            _logger.warning("-------------- here diff process ------------")
            diff_stock_list = []
            #query = "select id from isy_stock_report where serial_number not in " + closing_barcode_list + " and location_id not in " + external_location_ids
            
            obj_diff_stocks = self.env['isy.stock.report'].search([('serial_number','not in',closing_barcode_list),('location_id','not in',external_location_ids)])
            for obj_diff in obj_diff_stocks:
                diff_stock_list.append((0, 0, {
                    'name': obj_diff.serial_number,
                    'product_category': obj_diff.product_category.id,
                    'location_id': obj_diff.location_id.id,
                    'inventory_category': result.inventory_category,
                    'product_id': obj_diff.product_id.id,
                    'assigned_type': obj_diff.assigned_type,
                    'assigned_to': obj_diff.assigned_to.id,
                    'assigned_department': obj_diff.assigned_department.id,
                    'state': 'not_found',
                }))
            rec.update({'closing_stock_details': closing_stock_details_list, 'different_stock_details': diff_stock_list, 'remark': remark})
        _logger.info(
            "================load closing stock attachment data ended=================")

    def request_approval(self):
        for rec in self:
            rec.state = 'firstapproval'
    
    def cancel_process(self):
        for rec in self:
            rec.state = 'cancelled'


    def request_second_approval(self):
        for rec in self:
            if rec.first_approval.id == self.env.user.id:  
                rec.state = 'secondapproval'
            else:
                raise ValidationError(_("You are not allowed to approve this."))

    def process_done(self):
        for rec in self:
            if rec.second_approval.id == self.env.user.id:
                rec.state = 'done'
            else:
                raise ValidationError(
                    _("You are not allowed to approve this."))

            
class StockAuditingClosingStock(models.Model):
    _name = 'stock.auditing.closing.stock'
    _description = 'Closing Stock'

    name = fields.Char(string="Serial Number")
    stock_auditing_closing_id = fields.Many2one('stock.auditing')
    product_category = fields.Many2one('product.category', string="Product Type")
    location_id = fields.Many2one('stock.location', string="Location")
    inventory_category = fields.Selection(
        [('asset', 'Asset'), ('non-asset', 'Non-Asset')], string="Inventory Category")
    product_id = fields.Many2one(
        'product.product', string="Product Description")
    assigned_type = fields.Selection(
        [('employee', 'Employee'), ('student', 'Student')], string="Assigned Type")
    assigned_to = fields.Many2one("res.partner", string="Assigned Person")
    assigned_department = fields.Many2one(
        'hr.department', string="Assigned Department")

class StockAuditingDifferentStock(models.Model):
    _name = 'stock.auditing.different.stock'
    _description = "Stock Audit Different Stock"

    name = fields.Char(string="Serial Number")
    stock_auditing_different_id = fields.Many2one('stock.auditing')
    product_category = fields.Many2one(
        'product.category', string="Product Type")
    location_id = fields.Many2one('stock.location', string="Location")
    inventory_category = fields.Selection(
        [('asset', 'Asset'), ('non-asset', 'Non-Asset')], string="Inventory Category")
    product_id = fields.Many2one(
        'product.product', string="Product Description")
    assigned_type = fields.Selection(
        [('employee', 'Employee'), ('student', 'Student')], string="Assigned Type")
    assigned_to = fields.Many2one("res.partner", string="Assigned Person")
    assigned_department = fields.Many2one(
        'hr.department', string="Assigned Department")

    def stock_found(self):
        for rec in self:
            rec.state = 'founded'
    
    def stock_not_found(self):
        for rec in self:
            rec.state = 'not_found'


class ProductCategory(models.Model):
    _inherit = "product.category"

    is_it = fields.Boolean(string="Show on IT Inventory Gallery")


class ProductTemplate(models.Model):
    _inherit = "product.template"

    is_it = fields.Boolean(string="Show on IT Inventory Gallary")


class StockMassTransfer(models.Model):
    _name = 'stock.mass.transfer'

    location_from = fields.Many2one('stock.location','From Location')
    location_to = fields.Many2one('stock.location','To Location',required='1')
    require_assign_person = fields.Boolean(sring="Require Assign Person(?)")
    assigned_type = fields.Selection([('employee','Employee'),('student','Student')], string="Assigned Type")
    assigned_person = fields.Many2one('hr.employee', string="Assigned Person")
    assigned_student = fields.Many2one('res.partner',domain=[('student_number','!=',False)])

    @api.model
    def default_get(self,fields):
        res = super(StockMassTransfer, self).default_get(fields)
        active_ids = self._context.get('active_ids',[])
        active_objs = self.env['isy.stock.report'].browse(active_ids)
        locs = active_objs.mapped('location_id.id')
        if len(locs)>1:
            raise UserError('You can only transfer from the same location. \nPlease check the locations.')
        location_id = active_objs[0].location_id
        if location_id.require_assign_person:
            assigned_to=active_objs[0].assigned_to
            for rec in active_objs:
                if assigned_to.id!=rec.assigned_to.id:
                    raise UserError('You can only transfer from Personal Location of the same person.')

        res.update({'location_from':location_id.id})
        return res

    @api.onchange('location_to')
    def check_assign_person_require(self):
        if self.location_to:
            self.require_assign_person = self.location_to.require_assign_person
            if not self.require_assign_person:
                self.assigned_type = ''
                self.assigned_person = ''
                self.assigned_student = ''
            
    def transfer_multi_stock(self):
        active_objs = self.env['isy.stock.report'].browse(self._context.get('active_ids',[]))
        locs = active_objs.mapped('location_id.id')
        if len(locs)>1:
            raise UserError('You can only transfer from the same location. \nPlease check the locations.')
        vals = []
        for rec in active_objs:
            res = {
            'serial_number': rec.serial_number,
            'product_id': rec.product_id.id,
            'qty': 1,
            'assigned_department': rec.assigned_department.id,
            'inventory_category': rec.inventory_category,
            }
            vals.append([0,0,res])

        
        res = {
            'ist_details': vals,
            'ist_type':'out',
            'source_location': self.location_from.id,
            'destination_location': self.location_to.id,
            'require_assign_person': self.require_assign_person,
            'assigned_type':self.assigned_type,
            'assigned_person':self.assigned_person.id,
            'assigned_student':self.assigned_student.id,
            }

        if self.location_to.usage in ['inventory','customer']:
            first_approval = self.env['hr.employee'].search([('user_id','=',self.env.user.id)]).parent_id.user_id.id or False
            second_approval = self.location_to.second_approval.id or False
            res.update({
                'first_approval':first_approval,
                'second_approval':second_approval,
                'state':'firstapproval',
                })

        res_id = self.env['internal.stock.transfer'].create(res)
        res_id.check_assign_person_require()

        return {
            'name': 'Internal Stock Transfer',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'internal.stock.transfer',
            'res_id': res_id.id,
            # 'views': [(form_id.id, 'form')],
            'target': 'current',
            'domain': [],
            'context': {},
        }
