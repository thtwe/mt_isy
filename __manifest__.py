# -*- coding: utf-8 -*-
##############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#    Copyright (C) 2018-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Cybrosys Techno Solutions(<https://www.cybrosys.com>)
#
#    This program is free software: you can modify
#    it under the terms of the GNU Affero General Public License (AGPL) as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'MT ISY Enhancements',
    'version': '1.0.0',
    'summary': """Enhancements features""",
    'description': """
        1. Budget Display for Cost Center Manager
    """,
    'category': "Generic Modules/Tools",
    'author': 'MYAT THU',
    'company': 'ISY',
    'website': "https://www.isyedu.org",
    'depends': ['base', 'account', 'web', 'employee_expense_advance','hr_contract', 'hr_payroll', 'hr_payroll_account', 'hr_holidays', 'mail','portal', 'fail_safe', 'stock', 'accounting_budget_extension_V7'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/views.xml',
        'views/templates.xml',
        'views/stock_view.xml',
        'views/isy_approval_view.xml',
        'views/inventory_portal_template.xml',
        'views/schedule_return_list_portal_template.xml',
        'views/stock_report_portal_template.xml',
        'views/teacher_stock_report_portal_template.xml',
        'views/portal_payslip_process_request_template.xml',
        'views/accounting_budget_views.xml',
        'views/purchase_view.xml',
        'views/res_currency_view.xml',
        'views/account_payment_view.xml',
        'views/account_asset_view.xml',
        'views/isy_menu.xml',
        'views/account_move_view.xml',
        'views/studio_leave_views.xml',
        'views/studio_employee_views.xml',
        'views/studio_contract_views.xml',
        'wizard/budget_wizard_view.xml',
        'wizard/payroll_request_report_wizard_view.xml',
        'data/report_paperformat.xml',
        'data/mail_template_data.xml',
        'data/ir_sequence_data.xml',
        'data/ir_cron.xml',
        'report/employee_expense_advance_report.xml',
        'report/employee_expense_reimbursement_report.xml',
        'report/payslip_adjustment_details_report.xml',
        'report/employee_payable_receivable_report.xml',
        'report/account_move_report.xml',
        'report/purchase_report.xml',
        'report/advanced_report.xml',
        'report/opex_report.xml',
        'report/capex_report.xml',
        'report/stock_report.xml',
        'report/payroll_request_process_report.xml',
        
    ],
    "external_dependencies": {"python3": ["pyjwt"]},
    'images': [],
    'license': 'AGPL-3',
    'demo': [],
    'assets': {
        'web.assets_backend': [
            'mt_isy/static/src/js/mt_isy.js',
        ],
        'web.assets_frontend': [
            'mt_isy/static/src/css/isy_style.css',
        ],
    },
    'installable': True,
    'auto_install': False,
    'application': False,
}
