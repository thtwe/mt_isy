# -*- coding: utf-8 -*-
import time
from odoo import api, fields, models, tools, _
import datetime
from calendar import monthrange
from odoo.exceptions import ValidationError,UserError
from odoo.tools import float_compare, float_is_zero
import odoo.addons.decimal_precision as dp
import logging
_logger = logging.getLogger(__name__)

class BudgetDisplayCostManagerWizard(models.TransientModel):
    _name = 'budget.display.cost.manager.wizard'

    @api.model
    def default_get(self,fields):
        res = super(BudgetDisplayCostManagerWizard, self).default_get(fields)
        result = self.env['budget.display.cost.manager.result'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        return res

    def _get_current_fiscal_year(self):
        current_date = datetime.datetime.now().date()
        afy = self.env['account.fiscal.year'].search([('date_from','<=',str(current_date)),('date_to','>=',str(current_date))])[0]
        return afy.id

    def _get_group_budget_ccm_user(self):
        group_id = self.env.ref('mt_isy.group_budget_ccm_user').id
        user_ids = self.get_users_from_group(group_id)
        return [('id','in',user_ids)]

    def get_users_from_group(self,group_id):
        users_ids = []
        sql_query = """select uid from res_groups_users_rel where gid = %s"""                
        params = (group_id,)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.fetchall()
        for users_id in results:
            users_ids.append(users_id[0])
        return users_ids

    name = fields.Many2one('account.fiscal.year', string="Fiscal Year", default=_get_current_fiscal_year)
    user_id = fields.Many2one('res.users', string="Users", domain=_get_group_budget_ccm_user)

    def generate_budget_list(self):
        vals = []
        
        result = self.env['budget.display.cost.manager.result'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()

        #189
        # domain = []
        if not self.user_id:
            user_id = self.env.user
            # domain.append(('id','=',self.env.user.id))
        else:
            user_id = self.user_id
            # domain.append(('id','=',self.user_id.id))
        
        date_start = self.name.date_from
        date_end  = self.name.date_to

        product_ids = self.env['product.product'].search([('product_tmpl_id','in',user_id.user_product_ids.ids)])
        account_ids = product_ids.sudo().mapped('property_account_expense_id').filtered(lambda x: x.code.startswith('5'))
        # if self.user_id.id==2:
        if user_id.has_group('mt_isy.group_budget_cosolidated_user'):
            account_ids += self.env['account.account'].sudo().search([('code','=like','5%'),('id','not in',account_ids.ids),('company_id','in',[4,1])])
            # GALA account requested by SL
            account_ids += self.env['account.account'].sudo().search([('code','=','451006'),('company_id','in',[4,1])])
            _logger.debug(account_ids)
        
        if not account_ids:
            raise ValidationError(_("No records found."))
        query = """
        SELECT account_code,ARRAY_AGG(account_name) as account_name,SUM(planned_amount) as planned_amount,SUM(practical_amount) as practical_amount
        FROM (
            SELECT --acc.id as account_id,
                acc.code as account_code,
                acc.name as account_name,
                (planned_amount) as planned_amount,
                0 as practical_amount
            FROM budgetextension_budget b
            LEFT JOIN account_account acc on acc.id=b.account_id
            LEFT JOIN x_grouping gp on gp.id=b.x_studio_group
            WHERE acc.code in %s AND start_date>='start_date_str' AND b.end_date<='end_date_str'
            --GROUP BY acc.code,acc.name
            UNION ALL
            SELECT --acc.id as account_id,
                acc.code as account_code,
                acc.name as account_name,
                0 as planned_amount,
                (debit-credit) as practical_amount
            FROM account_move_line aml
            LEFT JOIN account_move am on am.id=aml.move_id
            LEFT JOIN account_account acc on acc.id=aml.account_id
            WHERE acc.code in %s AND am.state='posted' AND aml.date>='start_date_str' AND aml.date<='end_date_str'
            --GROUP BY acc.code,acc.name
        )A
        GROUP BY account_code
        ORDER BY account_code;
        """
        query = query.replace('start_date_str',str(date_start))
        query = query.replace('end_date_str',str(date_end))
        _logger.debug("start listing.")
        self.env.cr.execute(query %(tuple(account_ids.mapped('code')),tuple(account_ids.mapped('code'))))
        results = self.env.cr.dictfetchall()
        for res in results:
            account_code = res.get('account_code')
            account_names = res.get('account_name')
            if isinstance(account_names, list) and account_names:
                account_name = account_names[0]  # Take the first dictionary
            if isinstance(account_name, dict):
                    account_name = account_name.get('en_US') or list(account_name.values())[0]  # Extract name
            else:
                account_name = "" 
            planned_amount = res.get('planned_amount')
            practical_amount = res.get('practical_amount')
            if planned_amount!=0 or practical_amount!=0:
                vals.append({
                    "name": f"[{account_code}]-{account_name}",
                    "user_id": user_id.id,
                    # "group_id": x_studio_group,
                    "budget": planned_amount,
                    "actual": practical_amount,
                    "remaining": planned_amount - practical_amount,
                    # "budget_id": budget_id.get('id') or False,
                })
        _logger.debug("end listing.")



        # domain = [('start_date', '>=', date_start), ('end_date', '<=', date_end),('account_id', 'in', account_ids.ids)]
        # all_budget_ids = self.env['budgetextension.budget'].sudo().search_read(domain,['id','account_id','x_studio_group','planned_amount','practical_amount'])
        # _logger.debug("start listing.")
        # for account_id in account_ids:
        #     planned_amount = 0
        #     practical_amount = 0
        #     budget_ids = list(filter(lambda x:x.get('account_id') and x.get('account_id')[0]==account_id.id,all_budget_ids))
        #     budget_id = (budget_ids and budget_ids[0]) or {}
        #     planned_amount = budget_id.get('planned_amount') or 0

        #     practical_amount = budget_id.get('practical_amount') or 0

        #     x_studio_group = budget_id.get('x_studio_group') and budget_id.get('x_studio_group')[0] or False
        #     if planned_amount!=0 or practical_amount!=0:
        #         res = {
        #                 "name": '['+str(account_id.code)+']-'+account_id.name,
        #                 'group_id': x_studio_group,
        #                 "budget": planned_amount,
        #                 "actual": practical_amount,
        #                 "remaining": planned_amount - practical_amount,
        #                 "budget_id": budget_id.get('id') or False,
        #             }
        #         vals.append(res)
        # _logger.debug("end listing.")

        if vals:
            self.env['budget.display.cost.manager.result'].create(vals)
            wizard_form = self.env.ref('mt_isy.view_isy_budget_display_result', False)
            
            

            return {
                        'name': 'Budget',
                        'type': 'ir.actions.act_window',
                        'view_type': 'form',
                        'view_mode': 'tree',
                        'res_model': 'budget.display.cost.manager.result',
                        'views': [(wizard_form.id, 'tree')],            
                        'target': 'current',
                        'domain' : [('create_uid','=', self.env.user.id)],
                    }
        else:
            raise ValidationError(_("No records found."))

class BudgetDisplayCostManagerResult(models.TransientModel):
    _name = 'budget.display.cost.manager.result'

    name = fields.Char(string = 'Account')
    user_id = fields.Many2one('res.users',string='User')
    budget = fields.Float(string = 'Budget')
    actual = fields.Float(string = 'YTD')
    remaining = fields.Float(string='Remaining')
    group_id = fields.Many2one('x_grouping',string='Group')
    budget_id = fields.Many2one('budgetextension.budget',string='Extended Budget')


class BudgetDisplayConsolidatedWizard(models.TransientModel):
    _name = 'budget.display.consolidated.wizard'

    @api.model
    def default_get(self,fields):
        res = super(BudgetDisplayConsolidatedWizard, self).default_get(fields)
        result = self.env['budget.display.consolidated.result'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        return res

    def _get_current_fiscal_year(self):
        current_date = datetime.datetime.now().date()
        afy = self.env['account.fiscal.year'].search([('date_from','<=',str(current_date)),('date_to','>=',str(current_date))])[0]
        return afy.id

    def get_users_from_group(self,group_id):
        users_ids = []
        sql_query = """select uid from res_groups_users_rel where gid = %s"""                
        params = (group_id,)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.fetchall()
        for users_id in results:
            users_ids.append(users_id[0])
        return users_ids

    def _get_group_budget_ccm_user(self):
        group_id = self.env.ref('mt_isy.group_budget_ccm_user').id
        user_ids = self.get_users_from_group(group_id)
        return [('id','in',user_ids)]

    name = fields.Many2one('account.fiscal.year', string="Fiscal Year", default=_get_current_fiscal_year)
    user_id = fields.Many2one('res.users', string="Users", domain=_get_group_budget_ccm_user)

    def generate_budget_list(self):
        vals = []
        _logger.debug("start deleting.")
        result = self.env['budget.display.consolidated.result'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        _logger.debug("end deleting.")

        _logger.debug("start searching.")
        date_start = self.name.date_from
        date_end  = self.name.date_to
        # account_ids = self.env['account.account'].search([('account_type.internal_group','=','expense')])

        if not self.user_id:
            user_id = self.env.user
        else:
            user_id = self.user_id
        product_ids = self.env['product.product'].search([('product_tmpl_id','in',user_id.user_product_ids.ids)])
        account_ids = product_ids.sudo().mapped('property_account_expense_id').filtered(lambda x: x.code.startswith('5'))
        # if self.env.user.id==2:
        if user_id.has_group('mt_isy.group_budget_cosolidated_user'):
            account_ids += self.env['account.account'].sudo().search([('code','=like','5%'),('id','not in',account_ids.ids),('company_id','in',[4,1])])
            # GALA account requested by SL
            account_ids += self.env['account.account'].sudo().search([('code','=','451006'),('company_id','in',[4,1])])
            _logger.debug(account_ids)
        
        if not account_ids:
            raise ValidationError(_("No records found."))
        query = """
        SELECT account_code,ARRAY_AGG(account_name) as account_name,SUM(planned_amount_100) as planned_amount_100,SUM(planned_amount) as planned_amount,SUM(practical_amount) as practical_amount
        FROM (
            SELECT --acc.id as account_id,
                acc.code as account_code,
                acc.name as account_name,
                (planned_amount_100) as planned_amount_100,
                (planned_amount) as planned_amount,
                0 as practical_amount
            FROM budgetextension_budget b
            LEFT JOIN account_account acc on acc.id=b.account_id
            LEFT JOIN x_grouping gp on gp.id=b.x_studio_group
            WHERE acc.code in %s AND start_date>='start_date_str' AND b.end_date<='end_date_str'
            --GROUP BY acc.code,acc.name
            UNION ALL
            SELECT --acc.id as account_id,
                acc.code as account_code,
                acc.name as account_name,
                0 as planned_amount_100,
                0 as planned_amount,
                (debit-credit) as practical_amount
            FROM account_move_line aml
            LEFT JOIN account_move am on am.id=aml.move_id
            LEFT JOIN account_account acc on acc.id=aml.account_id
            WHERE acc.code in %s AND am.state='posted' AND aml.date>='start_date_str' AND aml.date<='end_date_str'
            --GROUP BY acc.code,acc.name
        )A
        GROUP BY account_code
        ORDER BY account_code;
        """
        query = query.replace('start_date_str',str(date_start))
        query = query.replace('end_date_str',str(date_end))
        _logger.debug("start listing.")
        self.env.cr.execute(query %(tuple(account_ids.mapped('code')),tuple(account_ids.mapped('code'))))
        results = self.env.cr.dictfetchall()
        for res in results:
            account_code = res.get('account_code')
            account_names = res.get('account_name')
            if isinstance(account_names, list) and account_names:
                account_name = account_names[0]  # Take the first dictionary
            if isinstance(account_name, dict):
                    account_name = account_name.get('en_US') or list(account_name.values())[0]  # Extract name
            else:
                account_name = "" 
            planned_amount = res.get('planned_amount')
            planned_amount_100 = res.get('planned_amount_100')
            practical_amount = res.get('practical_amount')
            if planned_amount!=0 or practical_amount!=0:
                vals.append({
                    "name": f"[{str(account_code)}]-{account_name}",
                    # "name": '['+str(account_code)+']-'+account_name,
                    "user_id": user_id.id,
                    # "group_id": x_studio_group,
                    "budget_100": planned_amount_100,
                    "budget": planned_amount,
                    "actual": practical_amount,
                    "remaining_100": planned_amount_100 - practical_amount,
                    "remaining": planned_amount - practical_amount,
                    # "budget_id": budget_id.get('id') or False,
                })
        _logger.debug("end listing.")


        # domain = [('start_date', '>=', date_start), ('end_date', '<=', date_end),('account_id', 'in', account_ids.ids)]
        # all_budget_ids = self.env['budgetextension.budget'].search_read(domain,['id','account_id','x_studio_group','planned_amount_100','planned_amount','practical_amount'])
        # _logger.debug("start listing.")
        # for account_id in account_ids:
        #     planned_amount = 0
        #     practical_amount = 0
        #     budget_ids = list(filter(lambda x:x.get('account_id') and x.get('account_id')[0]==account_id.id,all_budget_ids))
        #     budget_id = (budget_ids and budget_ids[0]) or {}
        #     planned_amount_100 = budget_id.get('planned_amount_100') or 0
        #     planned_amount = budget_id.get('planned_amount') or 0
        #     practical_amount = budget_id.get('practical_amount') or 0
        #     x_studio_group = budget_id.get('x_studio_group') and budget_id.get('x_studio_group')[0] or False
        #     if planned_amount!=0 or practical_amount!=0:
        #         res = {
        #                 "name": '['+str(account_id.code)+']-'+account_id.name,
        #                 'group_id': x_studio_group,
        #                 "budget_100": planned_amount_100,
        #                 "budget": planned_amount,
        #                 "actual": practical_amount,
        #                 "remaining_100": planned_amount_100 - practical_amount,
        #                 "remaining": planned_amount - practical_amount,
        #                 "budget_id": budget_id.get('id') or False,
        #             }
        #         vals.append(res)
        # _logger.debug("end listing.")


        if vals:
            _logger.debug("start creating.")
            self.env['budget.display.consolidated.result'].create(vals)
            _logger.debug("end creating.")
            wizard_form = self.env.ref('mt_isy.view_isy_budget_display_consolidated_result', False)
            
            return {
                        'name': 'Budget',
                        'type': 'ir.actions.act_window',
                        'view_type': 'form',
                        'view_mode': 'tree',
                        'res_model': 'budget.display.consolidated.result',
                        'views': [(wizard_form.id, 'tree')],            
                        'target': 'current',
                        'domain' : [('create_uid','=', self.env.user.id)],
                    }
        else:
            raise ValidationError(_("No records found."))


class BudgetDisplayConsolidatedResult(models.TransientModel):
    _name = 'budget.display.consolidated.result'

    name = fields.Char(string = 'Account')
    user_id = fields.Many2one('res.users',string='User')
    budget_100 = fields.Float(string = 'Budget (100%)')
    budget = fields.Float(string = 'Budget (85%)')
    actual = fields.Float(string = 'YTD')
    remaining = fields.Float(string='Remaining (85%)')
    remaining_100 = fields.Float(string='Remaining (100%)')
    group_id = fields.Many2one('x_grouping',string='Group')
    budget_id = fields.Many2one('budgetextension.budget',string='Extended Budget')


class BudgetDisplayCCMWizardCapex(models.TransientModel):
    _name = 'budget.display.ccm.wizard.capex'

    @api.model
    def default_get(self,fields):
        res = super(BudgetDisplayCCMWizardCapex, self).default_get(fields)
        result = self.env['budget.display.ccm.result.capex'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        return res

    def _get_current_fiscal_year(self):
        current_date = datetime.datetime.now().date()
        afy = self.env['account.fiscal.year'].search([('date_from','<=',str(current_date)),('date_to','>=',str(current_date))])[0]
        return afy.id

    def get_users_from_group(self,group_id):
        users_ids = []
        sql_query = """select uid from res_groups_users_rel where gid = %s"""                
        params = (group_id,)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.fetchall()
        for users_id in results:
            users_ids.append(users_id[0])
        return users_ids

    def _get_group_budget_ccm_user(self):
        group_id = self.env.ref('mt_isy.group_budget_ccm_user_capex').id
        user_ids = self.get_users_from_group(group_id)
        return [('id','in',user_ids)]

    name = fields.Many2one('account.fiscal.year', string="Fiscal Year", default=_get_current_fiscal_year)
    user_id = fields.Many2one('res.users', string="Users", domain=_get_group_budget_ccm_user)

    def generate_budget_list(self):
        vals = []
        _logger.debug("start deleting.")
        result = self.env['budget.display.ccm.result.capex'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        _logger.debug("end deleting.")
        if self.user_id:
            user_id = self.user_id
        else:
            user_id = self.env.user

        _logger.debug("start searching.")
        date_start = self.name.date_from
        date_end  = self.name.date_to

        group_id = self.env.ref('mt_isy.group_budget_cosolidated_user').id
        conso_user_ids = self.sudo().get_users_from_group(group_id)

        # account_ids = self.env['account.account'].search([('account_type.internal_group','=','expense')])
        # if self.user_id:
        #     product_ids = self.env['product.product'].search([('product_tmpl_id','in',self.user_id.user_product_ids.ids)])
        #     account_ids = product_ids.mapped('property_account_expense_id')

        domain = [('from_date', '>=', date_start), ('to_date', '<=', date_end),('type_id.name','ilike','expense')]
        all_budget_ids = self.env['capital.budget.template'].sudo().search(domain)
        _logger.debug("start listing.")
        for budget_id in all_budget_ids:
            #if b_acc.id in account_ids.ids:
            planned_amount = 0
            planned_amount = budget_id.planned_amount
            budget_group_id = self.env['x.capex.group'].sudo().search([('name','=',budget_id.name)])
            if user_id.id not in conso_user_ids and user_id.id not in budget_group_id.user_ids.ids:
                continue
            sequence = budget_group_id.sequence
            budget_accounts = budget_group_id.account_ids
            wip_accounts = self.env['account.account'].sudo().search([('workinprocess','=',True)])
                
            practical_amount = 0
            line_obj = self.env['account.move.line'].sudo()
            domain = ['&','&','&',('date','>=',date_start),('date','<=',date_end),('move_id.state','=','posted')
                    ,'|',('account_id','in',budget_accounts.ids), 
                    '&',('account_id', 'in', wip_accounts.ids),('capex_group_id.name','=',budget_id.name)]
            # if b_acc.sudo().workinprocess:
            #     domain += [('capex_group_id.name','=',rec.x_capex.x_name)]
            where_query = line_obj._where_calc(domain)
            # line_obj._apply_ir_rules(where_query, 'read')
            from_clause,  where_clause, where_clause_params = where_query.get_sql()
            # from_clause = '"account_move_line" LEFT JOIN "account_move" AS "account_move_line__move_id" ON ("account_move_line"."move_id" = "account_move_line__move_id"."id")'
            from_clause += ' LEFT JOIN account_account acc on acc.id=account_move_line.account_id'
            # where_clause = '(((("account_move_line"."date" >= %s) AND ("account_move_line"."date" <= %s)) AND ("account_move_line__move_id"."state" = %s)) AND (FALSE OR (("account_move_line"."account_id" in (%s)) AND ("account_move_line"."capex_group_id" in (SELECT "x_capex_group".id FROM "x_capex_group" WHERE ("x_capex_group"."name" = %s))))))'
            select = "SELECT SUM(CASE WHEN acc.account_type='Fixed Assets' AND account_move_line__move_id.journal_id=81 THEN (debit) ELSE (debit)-(credit) END) from " + from_clause + " where " + where_clause
            # select = "SELECT  (debit)-SUM(credit) from " + from_clause + " where " + where_clause
            self.env.cr.execute(select, where_clause_params)
            practical_amount = self.env.cr.fetchone()[0] or 0

            if planned_amount!=0 or practical_amount!=0:
                res = {
                        "name": budget_id.name,
                        "budget": planned_amount,
                        "actual": practical_amount,
                        "remaining": planned_amount - practical_amount,
                        "budget_id": budget_id.id,
                        "sequence": sequence,
                    }
                vals.append(res)

        _logger.debug("end listing.")
        if vals:
            _logger.debug("start creating.")
            self.env['budget.display.ccm.result.capex'].create(vals)
            _logger.debug("end creating.")
            wizard_form = self.env.ref('mt_isy.view_isy_budget_display_ccm_result_capex', False)
            
            return {
                        'name': 'Budget',
                        'type': 'ir.actions.act_window',
                        'view_type': 'form',
                        'view_mode': 'tree',
                        'res_model': 'budget.display.ccm.result.capex',
                        'views': [(wizard_form.id, 'tree')],            
                        'target': 'current',
                        'domain' : [('create_uid','=', self.env.user.id)],
                    }
        else:
            raise ValidationError(_("No records found."))


class BudgetDisplayCCMResultCapex(models.TransientModel):
    _name = 'budget.display.ccm.result.capex'
    _order = 'sequence'

    name = fields.Char(string = 'Account')
    budget = fields.Float(string = 'Budget')
    actual = fields.Float(string = 'YTD')
    remaining = fields.Float(string='Remaining')
    budget_id = fields.Many2one('capital.budget.template',string='Capital Budget')
    sequence = fields.Integer('Sequence',default=1)


class BudgetDisplayConsolidatedWizardCapex(models.TransientModel):
    _name = 'budget.display.consolidated.wizard.capex'

    @api.model
    def default_get(self,fields):
        res = super(BudgetDisplayConsolidatedWizardCapex, self).default_get(fields)
        result = self.env['budget.display.consolidated.result.capex'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        return res

    def _get_current_fiscal_year(self):
        current_date = datetime.datetime.now().date()
        afy = self.env['account.fiscal.year'].search([('date_from','<=',str(current_date)),('date_to','>=',str(current_date))])[0]
        return afy.id

    def get_users_from_group(self,group_id):
        users_ids = []
        sql_query = """select uid from res_groups_users_rel where gid = %s"""                
        params = (group_id,)
        self.env.cr.execute(sql_query, params)
        results = self.env.cr.fetchall()
        for users_id in results:
            users_ids.append(users_id[0])
        return users_ids

    def _get_group_budget_ccm_user(self):
        group_id = self.env.ref('mt_isy.group_budget_ccm_user').id
        user_ids = self.get_users_from_group(group_id)
        return [('id','in',user_ids)]

    name = fields.Many2one('account.fiscal.year', string="Fiscal Year", default=_get_current_fiscal_year)
    user_id = fields.Many2one('res.users', string="Users", domain=_get_group_budget_ccm_user)

    def generate_budget_list(self):
        vals = []
        _logger.debug("start deleting.")
        result = self.env['budget.display.consolidated.result.capex'].search([('create_uid','=',self.env.user.id)])
        if result:
            result.unlink()
        _logger.debug("end deleting.")
        if self.user_id:
            user_id = self.user_id
        else:
            user_id = self.env.user

        _logger.debug("start searching.")
        date_start = self.name.date_from
        date_end  = self.name.date_to
        group_id = self.env.ref('mt_isy.group_budget_cosolidated_user').id
        conso_user_ids = self.sudo().get_users_from_group(group_id)

        domain = [('from_date', '>=', date_start), ('to_date', '<=', date_end),('type_id.name','ilike','expense')]
        all_budget_ids = self.env['capital.budget.template'].search(domain)
        _logger.debug("start listing.")
        for budget_id in all_budget_ids:
            #if b_acc.id in account_ids.ids:
            planned_amount = 0
            planned_amount = budget_id.planned_amount
            planned_amount_100 = budget_id.planned_amount_100
            budget_group_id = self.env['x.capex.group'].search([('name','=',budget_id.name)])
            if user_id.id not in conso_user_ids and user_id.id not in budget_group_id.user_ids.ids:
                continue
            sequence = budget_group_id.sequence
            budget_accounts = budget_group_id.account_ids
            wip_accounts = self.env['account.account'].sudo().search([('workinprocess','=',True)])
                
            practical_amount = 0
            line_obj = self.env['account.move.line']
            domain = ['&','&','&',('date','>=','2024-08-01'),('date','<=',date_end),('move_id.state','=','posted')
                    ,'&',('account_id', 'in', wip_accounts.ids),('capex_group_id.name','=',budget_id.name)]
            # if b_acc.sudo().workinprocess:
            #     domain += [('capex_group_id.name','=',rec.x_capex.x_name)]
            where_query = line_obj._where_calc(domain)
            # line_obj._apply_ir_rules(where_query, 'read')
            from_clause,  where_clause, where_clause_params = where_query.get_sql()
            # from_clause = '"account_move_line" LEFT JOIN "account_move" AS "account_move_line__move_id" ON ("account_move_line"."move_id" = "account_move_line__move_id"."id")'
            from_clause += ' LEFT JOIN account_account acc on acc.id=account_move_line.account_id'
            # where_clause = '(((("account_move_line"."date" >= %s) AND ("account_move_line"."date" <= %s)) AND ("account_move_line__move_id"."state" = %s)) AND (FALSE OR (("account_move_line"."account_id" in (%s)) AND ("account_move_line"."capex_group_id" in (SELECT "x_capex_group".id FROM "x_capex_group" WHERE ("x_capex_group"."name" = %s))))))'
            select = "SELECT SUM((debit)) from " + from_clause + " where " + where_clause
            # select = "SELECT SUM(debit)-SUM(credit) from " + from_clause + " where " + where_clause
            # select = "SELECT SUM(CASE WHEN acc_type.name='Fixed Assets' AND account_move_line__move_id.journal_id=81 THEN (debit) ELSE (debit)-(credit) END) from " + from_clause + " where " + where_clause
            # select = "SELECT SUM(debit)-SUM(credit) from " + from_clause + " where " + where_clause
            self.env.cr.execute(select, where_clause_params)
            practical_amount = self.env.cr.fetchone()[0] or 0
            _logger.debug(f"Executing query: {select} with parameters: {where_clause_params}")

            if planned_amount!=0 or practical_amount!=0:
                res = {
                        "name": budget_id.name,
                        "budget": planned_amount,
                        "budget_100": planned_amount_100,
                        "actual": practical_amount,
                        "remaining": planned_amount - practical_amount,
                        "remaining_100": planned_amount_100 - practical_amount,
                        "budget_id": budget_id.id,
                        "sequence": sequence,
                    }
                vals.append(res)

        _logger.debug("end listing.")
        if vals:
            _logger.debug("start creating.")
            self.env['budget.display.consolidated.result.capex'].create(vals)
            _logger.debug("end creating.")
            wizard_form = self.env.ref('mt_isy.view_isy_budget_display_consolidated_result_capex', False)
            
            return {
                        'name': 'Budget',
                        'type': 'ir.actions.act_window',
                        'view_type': 'form',
                        'view_mode': 'tree',
                        'res_model': 'budget.display.consolidated.result.capex',
                        'views': [(wizard_form.id, 'tree')],            
                        'target': 'current',
                        'domain' : [('create_uid','=', self.env.user.id)],
                    }
        else:
            raise ValidationError(_("No records found."))


class BudgetDisplayConsolidatedResultCapex(models.TransientModel):
    _name = 'budget.display.consolidated.result.capex'
    _order = 'sequence'

    name = fields.Char(string = 'Account')
    budget = fields.Float(string = 'Budget (85%)')
    budget_100 = fields.Float(string = 'Budget (100%)')
    actual = fields.Float(string = 'YTD')
    remaining = fields.Float(string='Remaining (85%)')
    remaining_100 = fields.Float(string='Remaining (100%)')
    budget_id = fields.Many2one('capital.budget.template',string='Capital Budget')
    sequence = fields.Integer('Sequence',default=1)


class ExpenseSettlement(models.TransientModel):
    _name = 'expense.settlement'

    name = fields.Many2one('account.journal', string="Payment Method",domain=[('type','in',['cash','bank'])])
    amount = fields.Float(string="Settlement Amount")
    currency_id = fields.Many2one('res.currency', string= "Currency")

    def make_expense_settlement(self):
        obj_eae = self.env['employee.advance.expense'].search([('id','=',self._context.get('active_id'))])

        move_vals = self.get_move_vals(obj_eae)
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        vals = {
            'state': 'cleared',
            'settlement_move_id': move.id,
            'settlement_date': time.strftime('%Y-%m-%d'), 
            'settlement_account_by_id': self.env.user.id
        }
        obj_eae.write(vals)
        return True

    def get_move_vals(self,obj_eae):
        prec = self.env['decimal.precision'].precision_get('Account')
        if not  self.name.default_account_id:
                raise UserError(_("No Credit account found for the Journal, please configure one."))
        if not self.name.default_account_id:
                raise UserError(_("No Debit account found for the account, please configure one."))


        vals = []
        adv_cls_date = fields.Date.context_today(self)
        company_currency = obj_eae.company_id.currency_id
        current_currency = obj_eae.currency_id
        #usd amount
        # amount = current_currency.with_context({'date':obj_eae.account_validate_date}).compute(obj_eae.total_amount_expense, company_currency)
        amount = current_currency._convert(
            from_amount=obj_eae.total_amount_expense,
            to_currency=company_currency,
            company=self.env.company,
            date=obj_eae.account_validate_date
        )
        ref = obj_eae.name 
        move_line_debit = (0,0, {
            'name': ref,
            'account_id': obj_eae.account_id.id,
            'credit': 0.0 if float_compare(amount, 0.0, precision_digits=prec) > 0 else -amount,
            'debit': amount if float_compare(amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'journal_id': self.name.id,
            'partner_id': obj_eae.partner_id.id,
#                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
            'amount_currency': company_currency != current_currency and 1.0 * obj_eae.total_amount_expense or 0.0,
        })
        vals.append(move_line_debit)
        # cash_amount = current_currency.compute(obj_eae.total_amount_expense, company_currency)
        cash_amount = current_currency._convert(
            from_amount=obj_eae.total_amount_expense,
            to_currency=company_currency,
            company=self.env.company,
            date=obj_eae.account_validate_date
        )
        move_line_credit = (0,0, {
            'name': ref,
            'account_id': self.name.default_account_id.id,
            'debit': 0.0 if float_compare(cash_amount, 0.0, precision_digits=prec) > 0 else -cash_amount,
            'credit': cash_amount if float_compare(cash_amount, 0.0, precision_digits=prec) > 0 else 0.0,
            'journal_id': self.name.id,
            'partner_id': obj_eae.partner_id.id,
#                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'sale' else False,
            'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
            'amount_currency': company_currency != current_currency and -1.0 * obj_eae.total_amount_expense or 0.0,
        })
        vals.append(move_line_credit)

        #diff amount with usd
        diff_amount = cash_amount - amount
            
        if diff_amount:
            print("need to make exchange adjustment")
            account_id = obj_eae.company_id.currency_exchange_journal_id.default_account_id.id
            #convert usd to mmk
            diff_amount_currency = company_currency.compute(diff_amount,current_currency )
            gain_loss_diff = (0,0, {
                'name': ref,
                'account_id': account_id,
                'credit': 0.0 if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else -diff_amount,
                'debit': diff_amount if float_compare(diff_amount, 0.0, precision_digits=prec) > 0 else 0.0,
                'journal_id': self.name.id,
                'partner_id': obj_eae.partner_id.id,
#                 'analytic_account_id': category_id.account_analytic_id.id if category_id.type == 'purchase' else False,
                #'currency_id': current_currency.id if company_currency != current_currency else company_currency.id,
                #'amount_currency': company_currency != current_currency and diff_amount_currency if diff_amount_currency > 0 else -1 * diff_amount_currency or 0.0,
            })
            vals.append(gain_loss_diff)
        move_vals = {
            'ref': str(obj_eae.name) + "[Clearance]",
            'date': adv_cls_date or False,
            'journal_id': self.name.id,
            'narration':obj_eae.reason_for_advance,
            'line_ids': vals,
        }
        return move_vals

class BudgetDisplayCostManagerResultDummy(models.TransientModel):
    _name = 'budget.display.cost.manager.dummy'

    name = fields.Char(string = '#')



class HrPayslipApprovalGeneration(models.TransientModel):
    _name = 'hr.payslip.approval.generation'

    def _get_default_employee(self):
        obj_employee = self.env['hr.employee'].search([('user_id','=',self.env.user.id)])
        return obj_employee.id

    name = fields.Many2one('hr.employee',string="Request By", default=_get_default_employee)
    date_from = fields.Date(string="Request Date From")
    date_to = fields.Date(string="Request Date To")

    @api.onchange('date_from')
    def _onchange_date_from(self):
        if self.date_from:
            date_from = self.date_from
            last_day_of_month = date_from.replace(
                day=monthrange(date_from.year, date_from.month)[1])
            self.date_to = last_day_of_month
        else:
            self.date_to = False
        
    def generate_approval_request(self):
        _logger.info(
            "========================= Starting Payslip Approval Request ===================")
        given_date_from = self.date_from
        first_day_of_month = given_date_from.replace(day=1)
        if str(given_date_from) != str(first_day_of_month):
            raise ValidationError(_("Request date from must be first date of the month!"))
        given_date_to = self.date_to
        last_day_of_month = given_date_to.replace(
            day=monthrange(given_date_to.year, given_date_to.month)[1])
        
        if str(given_date_to) != str(last_day_of_month):
            raise ValidationError(_("Request date to must be last date of the month!"))

        if given_date_from.year != given_date_to.year or given_date_from.month != given_date_to.month:
            raise ValidationError(_("Request date from and request date to must be the same year and month!"))

        vals = {}
        val_details = []
        obj_hr_payslip_approval = self.env['hr.payslip.approval']

        obj_existing_records = obj_hr_payslip_approval.search([('date_from','=', self.date_from),('date_to','=', self.date_to), ('state','!=', 'cancelled')])
        if obj_existing_records:
            raise ValidationError(_("Already requested payslip approval for this date duration."))

        #1. Get first approval and second approval from ir.config.parameters
        #2. Get date from/to, request employee
        #3. Get active employees from contract
        #4. Validation
        #5. Create hr payslip approval and its details.
        first_approval_id = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.hrpayslipapproval_first_approval_employee', 0)
        obj_first_approval_employee = self.env['hr.employee'].search(
            [('id', '=', first_approval_id)]).id or False

        second_approval_id = self.env['ir.config_parameter'].sudo().get_param(
            'mt_isy.hrpayslipapproval_second_approval_employee', 0)
        obj_second_approval_employee = self.env['hr.employee'].search(
            [('id', '=', second_approval_id)]) or False

        date_from = self.date_from
        date_to = self.date_to
        request_employee_id = self.name.id
        #===================== Done for hrpayslipapproval header information=====================
        obj_contracts = self.env['hr.contract'].sudo().search([('state','in',['open','pending'])]).sudo()
        for obj_contract in obj_contracts:
            
            employee_type = 'local' if 'Local' in [
                x.name for x in obj_contract.employee_id.category_ids] else 'expatriate'
            if employee_type == 'local':
                annual_retirement = obj_contract.x_studio_local_annual_retirement_1
                monthly_retirement = obj_contract.x_studio_local_monthly_retirement_1
                contract_type = 'local100'
            else:
                annual_retirement = obj_contract.x_studio_expatriate_annual_retirement
                monthly_retirement = obj_contract.x_studio_expatriate_monthly_retirement
                if obj_contract.sudo().company_id.parent_id: # GTY
                    contract_type = 'expat40'
                else:# ISYA
                    contract_type = 'expat60'
            extra_duty_percent = obj_contract.extra_duty_allw
            val_details.append((0, 0, {
                'name': obj_contract.employee_id.id,
                'employee_type': employee_type,
                'job_title': obj_contract.x_studio_job_title_1,
                'wage': obj_contract.wage,
                'monthly_salary': obj_contract.x_studio_monthly_salary,
                'annual_retirement': annual_retirement if not obj_contract.unpaid_retirement else 0,
                'monthly_retirement': monthly_retirement if not obj_contract.unpaid_retirement else 0,
                'extra_duty_percent': extra_duty_percent,
                'contract_type':contract_type
            }))
        vals.update(
            {
                'date_from': date_from,
                'date_to': date_to,
                'request_employee_id': request_employee_id,
                'first_approval': first_approval_id,
                'second_approval': second_approval_id,
                'hr_payslip_approval_details': val_details,
            }
        )
        obj_hr_payslip_approval.create(vals)
        _logger.info("========================= End Payslip Approval Request ===================")
        return True
