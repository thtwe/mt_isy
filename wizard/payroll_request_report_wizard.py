# -*- coding: utf-8 -*-
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from odoo import api, fields, models, tools, _
from odoo.exceptions import ValidationError, UserError
from io import BytesIO
import base64
import pytz

try:
    import xlwt
    from xlwt import Borders
except ImportError:
    xlwt = None

import logging
_logger = logging.getLogger(__name__)


CASH_ALLOCATION_TYPE = [
    ('all', 'All'),
    ('local_bank_$', 'Deposit into Local Bank (USD account)'),
    ('local_bank_mmk', 'Amount in USD to be deposited into Kyat bank account'),
    ('local_bank_ks', 'Amount in USD to be converted into Kyat cash'),
    ('cash_usd', 'Amount in USD to be paid in USD cash'),
    ('401_k', '401K Allocation'),
    ('overseas_bank', 'Overseas Bank'),
    # ('donation_uws','Donation to United World Schools'),
    ('donation_yas','Donation to Yangon Animal Shelter'),
    ('donation_clc','Donation to Care to the Least Center - CLC Family'),
    ('donation_chinthe','Donation to Chinthe Fund'),
    ('savings_for_education','College Education Saving Program Deduction'),
    ('gala_usd','Amount in USD to pay for ISY Gala Ticket(s) - $50 Each'),
]
ADJ_TYPE = [('all','All'),('school_trip', 'School Trip'), ('tuition_fee', 'Tuition Fee'), ('other', 'Other')]

ALL_TYPE = [
    ('all', 'All'), 
    ('school_trip', 'School Trip'), 
    ('tuition_fee','Tuition Fee'), 
    ('other', 'Other'),
    ('local_bank_$', 'Deposit into Local Bank (USD account)'),
    ('local_bank_mmk', 'Amount in USD to be deposited into Kyat bank account'),
    ('local_bank_ks', 'Amount in USD to be converted into Kyat cash'),
    ('cash_usd', 'Amount in USD to be paid in USD cash'),
    ('401_k', '401K Allocation'),
    ('overseas_bank', 'Overseas Bank'),
    # ('donation_uws','Donation to United World Schools'),
    ('donation_yas','Donation to Yangon Animal Shelter'),
    ('donation_clc','Donation to Care to the Least Center - CLC Family'),
    ('donation_chinthe','Donation to Chinthe Fund'),
    ('savings_for_education','College Education Saving Program Deduction'),
    ('gala_usd','Amount in USD to pay for ISY Gala Ticket(s) - $50 Each'),
]
class PayrollRequestReport(models.TransientModel):
    _name = "payroll.request.report"

    date_from = fields.Date(string = "Date From", required = True)
    date_to = fields.Date( string = "Date To", required = True)
    by_employee_type = fields.Selection([('custom','Custom'),('all', 'All')],default='all')
    payroll_request_employee_details = fields.One2many('payroll.request.report.employees', 'prr_emp_id', string="Employee Details")
    cash_allocation_type = fields.Selection(CASH_ALLOCATION_TYPE, string="Cash Allocation Type", default='all', required="1")
    adjustment_type = fields.Selection(ADJ_TYPE, string="Adjustment Type", default='all', required="1")
    datas = fields.Binary('File')

    def print_report_payroll_request(self):
        workbook = xlwt.Workbook()
        borders = Borders()
        #borders.left,borders.right,borders.top = Borders.THIN,Borders.THIN,Borders.THIN
        #right_border = Borders()
        #right_border.right = Borders.THIN

        worksheet = workbook.add_sheet("Payroll Request Report",cell_overwrite_ok=True)
        worksheet.panes_frozen = True
        worksheet.remove_splits = True
        worksheet.horz_split_pos = 7
        header_bold = xlwt.easyxf("font: bold on, height 230; pattern: pattern solid, fore_colour white; alignment: horizontal center,vertical center; border: left thin,right thin,top thin,bottom thin;")
        header_title = xlwt.easyxf("font: bold on, height 230; pattern: pattern solid, fore_colour white; alignment: horizontal left; border: left thin,right thin,top thin,bottom thin;")
        conditon_style = xlwt.easyxf("font: bold on; pattern: pattern solid, fore_colour red;")

        worksheet.row(0).height = 400
        worksheet.row(1).height = 400
        worksheet.row(2).height = 400
        worksheet.row(3).height = 400
        worksheet.row(5).height = 400

        def get_width(num_characters):
            return int((1+num_characters) * 512)

        worksheet.write_merge(0, 2, 0, 4, 'ISY Payroll Request Process Report',header_bold)
        worksheet.write_merge(3,4,0,4,'From : %s To : %s '%(self.date_from,self.date_to),header_bold)

        headers = ['Employee Name', 'Description', 'Amount','Reference', 'Requested Time (GMT+6:30)']
        column = 0
        for header in headers:
            worksheet.write_merge(5,6,column,column,header,header_bold)
            if len(header) > 5:
                worksheet.col(column).width = get_width(len(header)+4)
            column+=1
        # headers2=['Opening','Stock In','Stock Out','Closing']
        # for header2 in headers2:
        #     col_merge=column
        #     col_merge+=1
        #     worksheet.write_merge(5,5,column,col_merge,header2,header_bold)
        #     column+=2

        # headers3=['Qty','Amount','Qty','Amount','Qty','Amount','Qty','Amount']
        # col=2
        # for header3 in headers3:
        #     worksheet.write(6,col,header3,header_bold)
        #     col+=1
        datetime_from = str(self.date_from) + " 00:00:01"
        datetime_to = str(self.date_to) + " 23:59:59"
        last_record_lists = []
        all_record_lists = []
        result_record_lists = []
        filter_allocation_type = []
        filter_adjustment_type = []
        #last records for cash allocation
        if self.by_employee_type != 'all':
            obj_emp_list_ids = [str(rec.name.id) for rec in self.payroll_request_employee_details]
            temp_employee_lists = str(tuple(obj_emp_list_ids))
            employee_lists = temp_employee_lists[0:-2] + ")"
            query = """
                select distinct on (hrppr.request_employee_id) hrppr.request_employee_id, hre.name as employee, hrppr.id, hrppr.name, hrppr.create_date from hr_payslip_process_request hrppr \
                inner join hr_employee hre on hre.id=hrppr.request_employee_id \
                where hrppr.request_employee_id in \
            """ + employee_lists + """ and hrppr.state='done' and hrppr.create_date >= '""" \
                + datetime_from + """' and hrppr.create_date <= '""" + \
                    datetime_to + """' ORDER BY hrppr.request_employee_id, hrppr.id DESC;"""
            self.env.cr.execute(query)
            last_record_lists = self.env.cr.dictfetchall()
        else:
            query = """
                select distinct on (hrppr.request_employee_id) hrppr.request_employee_id, hre.name as employee, hrppr.id, hrppr.name, hrppr.create_date from hr_payslip_process_request hrppr \
                inner join hr_employee hre on hre.id=hrppr.request_employee_id \
                where hrppr.state='done' and hrppr.create_date >= '""" \
                + datetime_from + """' and hrppr.create_date <= '""" + \
                    datetime_to + """' ORDER BY hrppr.request_employee_id, hrppr.id DESC;"""
            self.env.cr.execute(query)
            last_record_lists = self.env.cr.dictfetchall()
        
        #cash allocation
        if self.cash_allocation_type != 'all':
            filter_allocation_type.append(self.cash_allocation_type)
            val_filter_allocation_type = str(
                tuple(filter_allocation_type))[0:-2] + ")"
        else:
            filter_allocation_type = ['local_bank_$','local_bank_mmk', 'local_bank_ks','cash_usd', '401_k', 'overseas_bank','donation_uws','donation_yas','donation_clc','donation_chinthe','savings_for_education','gala_usd']        
            val_filter_allocation_type = str(tuple(filter_allocation_type))
        for lrl in last_record_lists:
            query = """
                select  name, amount from hr_payslip_cash_allocation_requests where amount > 0 and hr_payslip_process_request_id =
            """ + str(lrl['id']) + """ and name in """ + val_filter_allocation_type
            self.env.cr.execute(query)
            sub_res = self.env.cr.dictfetchall()
            if sub_res:
                lrl['report_details'] = sub_res

        #all records for deduction details
        if self.by_employee_type != 'all':
            obj_emp_list_ids = [str(rec.name.id) for rec in self.payroll_request_employee_details]
            temp_employee_lists = str(tuple(obj_emp_list_ids))
            employee_lists = temp_employee_lists[0:-2] + ")"
            query = """
                select hrppr.request_employee_id, hre.name as employee, hrppr.id, hrppr.name, hrppr.create_date from hr_payslip_process_request hrppr \
                inner join hr_employee hre on hre.id=hrppr.request_employee_id \
                where hrppr.request_employee_id in \
            """ + employee_lists + """ and hrppr.state='done' and hrppr.create_date >= '""" \
                + datetime_from + """' and hrppr.create_date <= '""" + \
                    datetime_to + """' ORDER BY hrppr.request_employee_id, hrppr.id DESC;"""
            self.env.cr.execute(query)
            all_record_lists = self.env.cr.dictfetchall()
        else:
            query = """
                select hrppr.request_employee_id, hre.name as employee, hrppr.id, hrppr.name, hrppr.create_date from hr_payslip_process_request hrppr \
                inner join hr_employee hre on hre.id=hrppr.request_employee_id \
                where hrppr.state='done' and hrppr.create_date >= '""" \
                + datetime_from + """' and hrppr.create_date <= '""" + \
                    datetime_to + """' ORDER BY hrppr.request_employee_id, hrppr.id DESC;"""
            self.env.cr.execute(query)
            all_record_lists = self.env.cr.dictfetchall()
 
        #deduction details
        if self.adjustment_type != 'all':
            filter_adjustment_type.append(self.adjustment_type)
            val_filter_adjustment_type = str(
                tuple(filter_adjustment_type))[0:-2] + ")"
        else:
            filter_adjustment_type = ['school_trip','tuition_fee', 'other']
            val_filter_adjustment_type = str(tuple(filter_adjustment_type))
        for arl in all_record_lists:
            query = """
                select  deduction_type as name, amount from hr_payslip_deduction_details where amount > 0 and hr_payslip_deduction_request_id =
            """ + str(arl['id']) + """ and deduction_type in """ + val_filter_adjustment_type
            self.env.cr.execute(query)
            sub_res = self.env.cr.dictfetchall()
            if sub_res:
                arl['report_details'] = sub_res
        
        
        result_record_lists += last_record_lists
        result_record_lists += all_record_lists
        
        sorted_result_record_lists = sorted(
            result_record_lists, key=lambda k: k['request_employee_id'])


        sheet_result_record_lists = list(filter(lambda i: 'report_details' in i.keys(), sorted_result_record_lists))

        row, col = 7, 0

        for result in sheet_result_record_lists:            
            for sub_result in result['report_details']:
                dt = datetime.strptime(
                    str(result['create_date']), '%Y-%m-%d %H:%M:%S.%f')
                old_tz = pytz.timezone('UTC')
                new_tz = pytz.timezone('Asia/Yangon')
                dt = old_tz.localize(dt).astimezone(new_tz)
                create_date_after_convert_time_zone= datetime.strftime(dt, '%Y-%m-%d %H:%M:%S')
                worksheet.write(row, 0, result['employee'])
                worksheet.write(row, 1,  dict(ALL_TYPE).get(sub_result['name']))
                worksheet.write(row, 2, sub_result['amount'])
                worksheet.write(row, 3, result['name'])
                worksheet.write(row, 4, create_date_after_convert_time_zone)
                row += 1

        fp = BytesIO()
        workbook.save(fp)
        fp.seek(0)
        stock_file = base64.b64encode(fp.read())
        self.write({'datas': stock_file})
        fp.close()
        
        _logger.info("Download URL: %s", '/web/binary/download_document?model=payroll.request.report&field=datas&id=%s&filename=payroll_request_report.xls' % (self.id))

        return {
            'type': 'ir.actions.act_url',
            'url':   '/web/binary/download_document?model=payroll.request.report&field=datas&id=%s&filename=payroll_request_report.xls' % (self.id),
            'target': 'new',
        }

class PayrollRequestReportEmployees(models.TransientModel):
    _name = "payroll.request.report.employees"

    name = fields.Many2one('hr.employee', string="Employee")
    prr_emp_id = fields.Many2one('payroll.request.report', string="Payroll Request Report Employee")
