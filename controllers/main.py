# -*- coding: utf-8 -*-
import io
import re

from PyPDF2 import PdfFileReader, PdfFileWriter

from odoo.http import request, route, Controller, content_disposition
from odoo.tools.safe_eval import safe_eval
from odoo.addons.hr_payroll.controllers.main import HrPayroll
from odoo.exceptions import AccessError, MissingError
from odoo.tools import consteq

import odoo
from odoo import http, _, fields as odoo_fields, tools, SUPERUSER_ID
from odoo.http import request, Response
from odoo.addons.web.controllers import main
from odoo.addons.account.controllers.portal import PortalAccount
import json
from odoo.service import db, security
import jwt
import logging
_logger = logging.getLogger(__name__)



class HrPayroll1(HrPayroll):

    @route(["/print/payslips"], type='http', auth='user')
    def get_payroll_report_print(self, list_ids='', **post):
        
        # if not request.env.user.has_group('hr_payroll.group_hr_payroll_user') or not list_ids or re.search("[^0-9|,]", list_ids):
        #     return request.not_found()

        ids = [int(s) for s in list_ids.split(',')]
        payslips = request.env['hr.payslip'].browse(ids)

        pdf_writer = PdfFileWriter()

        for payslip in payslips:
            report = request.env.ref('mt_isy.report_payslip_adjustment_details', False)
            
            report = report.with_context(lang=payslip.employee_id.sudo().address_home_id.lang)
            pdf_content, _ = report.sudo()._render_qweb_pdf(payslip.id, data={'company_id': payslip.company_id})
            reader = PdfFileReader(io.BytesIO(pdf_content), strict=False, overwriteWarnings=False)

            for page in range(reader.getNumPages()):
                pdf_writer.addPage(reader.getPage(page))

        _buffer = io.BytesIO()
        pdf_writer.write(_buffer)
        merged_pdf = _buffer.getvalue()
        _buffer.close()

        if len(payslips) == 1 and payslips.struct_id.report_id.print_report_name:
            report_name = safe_eval(payslips.struct_id.report_id.print_report_name, {'object': payslips})
        else:
            report_name = "Payslips"

        pdfhttpheaders = [
            ('Content-Type', 'application/pdf'),
            ('Content-Length', len(merged_pdf)),
            ('Content-Disposition', content_disposition(report_name + '.pdf'))
        ]

        return request.make_response(merged_pdf, headers=pdfhttpheaders)

class AccountInvoiceController(http.Controller):

    # @http.route("/check_method_get", auth='none', type='http',method=['GET'])
    # def check_method_get(self,**values):
    #     headers = {'Content-Type': 'application/json'}
    #     body = { 'results': { 'code':200, 'message':'OK' } }

    #     return Response(json.dumps(body), headers=headers)

    # 1. Define allow_domain_ps
    # 2. Define ps_api_decode_secret
    # 3. Define ps_student_decode_secret
    # 4. Define database.db_name
    @http.route('/invoices', methods=['POST'], csrf=False, type='http', auth="none")
    def print_id(self, **kw):
        #check allow url or not
        # allow_url = request.env['ir.config_parameter'].sudo().get_param('allow_domain_ps') or False
        # _logger.info(request.httprequest.environ)
        # if request.httprequest.environ.get('REMOTE_ADDR') != allow_url:
        #     if allow_url == False:
        #         status = {'code': 401, 'description': "Unauthorized. Please contact to system administrator to define allow url."}
        #     else:
        #         status = {'code': 401, 'description': "Unauthorized. Request URL is not allowed."}
        #     return json.dumps(status)
        #get api token and decryption by using HS256 JWT auth

        #b'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VybmFtZSI6Im9kb29hZG1pbkBpc3llZHUub3JnIiwicGFzc3dvcmQiOiJPZDAwQGRtIW4yMDIwIn0.drO_eJxRdVMwuZDc7irNHzLOIGfsEGET1cYE6pL1bT0'
        # 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VybmFtZSI6Im9kb29hZG1pbkBpc3llZHUub3JnIiwicGFzc3dvcmQiOiIyMDIyT2QwMEBkbSFuIn0.YN6dssWrVCSZMzi4Ytw0tRdzXMIyJUSGpbuIyne8eDg'
        #get encrypted api-key

        encoded_jwt = request.httprequest.headers.get('Api-Key') or False
    
        #encoded_jwt = request.httprequest.headers.get('Api-Key') or False
        #decode username and password dict
        credential_dict = jwt.decode(encoded_jwt, '3498CA36F63D31C8C5311BB657C8B', algorithms=['HS256'])

        username = credential_dict['username']
        password = credential_dict['password']
        database = request.env['ir.config_parameter'].sudo().get_param('database.db_name') or False
        if database == False:
            status = {'code': 401, 'description': "Unauthorized. Please contact to system administrator to define default database."}
            return json.dumps(status)
        result = main.Session.authenticate(self, database, username, password)
        if not result.get('uid'):
            status = {'code': 401, 'description': "Unauthorized Api Token."}
            return json.dumps(status)

        # jwt.encode({"enc_student_id": "106365"}, "3498CA36F63D31C8C5311BB657C8B", algorithm="HS256")
        # {"student_id":"106365",'enc_student_id':'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbmNfc3R1ZGVudF9pZCI6IjEwNjM2NSJ9.P9Dc5iYufHK9mxuWpCsDsXE660-FTL8amruxkUZ8rKo'}
        student_id = kw['student_id']
        #matching actual student_id and encrypted student id 105957
        #eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJlbmNfc3R1ZGVudF9pZCI6MTA1OTU3fQ.fWudP2jy2HvMeUDLgCM-gpzPwEsHN2vjAfQ-Etr7B9I
        enc_student_id_dict = jwt.decode(kw['enc_student_id'], '3498CA36F63D31C8C5311BB657C8B', algorithms=['HS256'])
        enc_student_id = enc_student_id_dict['enc_student_id']
        if int(student_id) == int(enc_student_id):
            partner_student_id = request.env['res.partner'].search([('student_number', '=', student_id)])
            if not partner_student_id:
                status = {'code': 404, 'description': "Not Found. Student does not exist in Odoo."}
                return json.dumps(status)
            last_invoice_id = request.env['account.move'].search([('partner_id', '=', partner_student_id.id),('move_type','=','out_invoice')], limit=1, order='id desc')
            if not last_invoice_id:
                status = {'code': 404, 'description': "Not Found. There has no invoice for this student."}
                return json.dumps(status)
            data = '["/report/pdf/account.report_invoice_with_payments_23_24/%s","qweb-pdf"]' % (last_invoice_id.id,)
            #response = main.ReportController.report_download(main.ReportController(), data, request.session.session_token)
            response = main.ReportController.report_download(main.ReportController(), data)
            return response
        else:
            status = {'code': 404, 'description': "Not Found. Unauthorized student id."}
            return json.dumps(status)

    @http.route('/products', methods=['POST'], csrf=False, type='http', auth="none")
    def get_product_list(self,**kw):
        #get encrypted api-key
        encoded_jwt = request.httprequest.headers.get('Api-Key') or False
        if encoded_jwt:
            #decode username and password dict
            credential_dict = jwt.decode(encoded_jwt, '3498CA36F63D31C8C5311BB657C8B', algorithms=['HS256'])

            username = credential_dict['username']
            password = credential_dict['password']
            database = request.env['ir.config_parameter'].sudo().get_param('database.db_name') or False
            if database == False:
                status = {'code': 401, 'description': "Unauthorized. Please contact to system administrator to define default database."}
                return json.dumps(status)
            result = main.Session.authenticate(self, database, username, password)
            if not result['session_id']:
                status = {'code': 401, 'description': "Unauthorized Api Token."}
                return json.dumps(status)
        else:
            status = {'code': 401, 'description': "Unauthorized Api Token."}
            return json.dumps(status)
            
        stock_objs = request.env['isy.stock.report'].sudo().search([('location_id.usage','=','internal')])

        query = """
                SELECT pt.name AS pname, product_id,
                    catg.name AS cname, product_category as category_id,
                    COUNT(*) AS total_qty,
                    SUM(CASE WHEN stock.user_email IS NULL THEN 1 ELSE 0 END) AS avail_qty,
                    SUM(CASE WHEN stock.user_email IS NOT NULL THEN 1 ELSE 0 END) AS reserved_qty
                FROM isy_stock_report stock
                LEFT JOIN product_product pp ON pp.id=stock.product_id
                LEFT JOIN product_template pt ON pt.id=pp.product_tmpl_id
                LEFT JOIN stock_location loc ON loc.id=stock.location_id
                LEFT JOIN product_category catg ON catg.id=stock.product_category
                WHERE loc.usage='internal' and (catg.is_it=True OR pt.is_it=True)
                GROUP BY pt.name,product_id,catg.name,product_category
                ORDER BY pt.name;
                """
        request.env.cr.execute(query)
        product_obj = request.env['product.product'].sudo()
        records = request.env.cr.dictfetchall()
        results = []
        product_ids = [r.get('product_id') for r in records]
        image_dt = product_obj.search_read([('id','in',product_ids)],['image_small'])
        for record in records:
            image = list(filter(lambda x:x.get('id')==record.get('product_id'),image_dt))[0].get('image_small')
            results.append({**record,'image':image.decode('utf-8') if image else ''})
        return json.dumps({'code': 200,'description':'Success','data':results})

    @http.route('/products/reserve/<int:product_id>/<string:user_email>', methods=['POST'], csrf=False, type='http', auth="none")
    def get_product_reserve(self,product_id,user_email,**kw):
        #get encrypted api-key
        encoded_jwt = request.httprequest.headers.get('Api-Key') or False
        if encoded_jwt:
            #decode username and password dict
            credential_dict = jwt.decode(encoded_jwt, '3498CA36F63D31C8C5311BB657C8B', algorithms=['HS256'])

            username = credential_dict['username']
            password = credential_dict['password']
            database = request.env['ir.config_parameter'].sudo().get_param('database.db_name') or False
            if database == False:
                status = {'code': 401, 'description': "Unauthorized. Please contact to system administrator to define default database."}
                return json.dumps(status)
            result = main.Session.authenticate(self, database, username, password)
            if not result['session_id']:
                status = {'code': 401, 'description': "Unauthorized Api Token."}
                return json.dumps(status)
        else:
            status = {'code': 401, 'description': "Unauthorized Api Token."}
            return json.dumps(status)

        _logger.debug('##### Reserve Process')
        _logger.debug(product_id)
        _logger.debug(user_email)
        stock_obj = request.env['isy.stock.report'].sudo().search([('product_id','=',product_id),('user_email','=',False)], limit=1)
        
        if not stock_obj:
            response = {'code': 404, 'description': "There is no product that can be reserved. Please contact to admin."}
            return json.dumps(response)
        stock_obj.write({'user_email': user_email})
        template = request.env.ref('mt_isy.stock_reserve_inventory_user_noti')
        request.env['mail.template'].sudo().browse(template.id).send_mail(stock_obj.id)
        response = {'code': 200, 'description': "You have already reserved "+stock_obj.serial_number+" of "+stock_obj.product_id.name+"."}
        return json.dumps(response)
    
    @http.route('/products/cancel/<int:product_id>/<string:user_email>', methods=['POST'], csrf=False, type='http', auth="none")
    def get_product_cancel(self,product_id,user_email):
        #get encrypted api-key
        encoded_jwt = request.httprequest.headers.get('Api-Key') or False
        if encoded_jwt:
            #decode username and password dict
            credential_dict = jwt.decode(encoded_jwt, '3498CA36F63D31C8C5311BB657C8B', algorithms=['HS256'])

            username = credential_dict['username']
            password = credential_dict['password']
            database = request.env['ir.config_parameter'].sudo().get_param('database.db_name') or False
            if database == False:
                status = {'code': 401, 'description': "Unauthorized. Please contact to system administrator to define default database."}
                return json.dumps(status)
            result = main.Session.authenticate(self, database, username, password)
            if not result['session_id']:
                status = {'code': 401, 'description': "Unauthorized Api Token."}
                return json.dumps(status)
        else:
            status = {'code': 401, 'description': "Unauthorized Api Token."}
            return json.dumps(status)
        
        _logger.debug('##### Cancel Process')
        _logger.debug(product_id)
        _logger.debug(user_email)
        # clear user_email when return back to IT Inventory
        stock_obj = request.env['isy.stock.report'].sudo().search([('product_id','=',product_id),('user_email','=',user_email)])
        if not stock_obj:
            response = {'code': 404, 'description': "There is no product that had been reserved by you. Please contact to admin."}
            return json.dumps(response)
        #already checked out, email notify 
        elif len(stock_obj)==1 and  stock_obj.location_id.name != 'A10 IT Storage':
            template = request.env.ref('mt_isy.stock_cancel_inventory_user_noti_tocheckin')
            request.env['mail.template'].sudo().browse(template.id).send_mail(stock_obj.id)
            response = {'code': 200, 'description': "Please return this product to IT Inventory."}
            return json.dumps(response)
        elif len(stock_obj)==1:
            template = request.env.ref('mt_isy.stock_cancel_inventory_user_noti')
            request.env['mail.template'].sudo().browse(template.id).send_mail(stock_obj.id)
            stock_obj.write({'user_email':False})
            response = {'code':200, 'description': "Success"}
            return json.dumps(response)
        elif len(stock_obj)>1:
            s_obj = stock_obj.filtered(lambda x: x.location_id.name == 'A10 IT Storage')
            if s_obj:
                template = request.env.ref('mt_isy.stock_cancel_inventory_user_noti')
                request.env['mail.template'].sudo().browse(template.id).send_mail(s_obj[0].id)
                s_obj[0].write({'user_email':False})
                response = {'code':200, 'description': "Success"}
                return json.dumps(response)
            else:
                template = request.env.ref('mt_isy.stock_cancel_inventory_user_noti_tocheckin')
                request.env['mail.template'].sudo().browse(template.id).send_mail(stock_obj[0].id)
                response = {'code': 200, 'description': "Please return this product to IT Inventory."}
                return json.dumps(response)


class CustomerPortalISY(PortalAccount):

    @http.route(['/my/journalentry/<int:invoice_id>'], type='http', auth="public", website=True)
    def portal_my_journalentry_detail(self, invoice_id, access_token=None, report_type=None, download=False, **kw):
        try:
            invoice_sudo = self._document_check_access('account.move', invoice_id, access_token)
        except (AccessError, MissingError):
            return request.redirect('/my')
        if report_type in ('html', 'pdf', 'text'):
            return self._show_report(model=invoice_sudo, report_type=report_type, report_ref='mt_isy.report_account_move_amn_custom', download=download)

        values = self._invoice_get_page_view_values(invoice_sudo, access_token, **kw)
        return request.render("account.portal_invoice_page", values)
