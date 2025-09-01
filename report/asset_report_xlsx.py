# models/asset_xlsx_export.py
import io
import base64
import xlsxwriter
from odoo import models, fields

class AccountAsset(models.Model):
    _inherit = "account.asset"

    dummy = fields.Binary("Dummy")  # needed for /web/content

    def export_assets_xlsx(self, record_ids):
        records = self.browse(record_ids)
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet("Assets Report")
        # Formats
        header_format = workbook.add_format({'bold': True, 'bg_color': '#CCCCCC', 'border': 1})
        num_format = workbook.add_format({'num_format': '#,##0.00', 'border': 1})
        text_format = workbook.add_format({'border': 1})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd', 'border': 1})


        # write headers
        headers = ["Asset Name", "Model/ Display Name", "Acquisition Date", "Original Value", "Net Book Value", "Accumulated Depreciation"]
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        # write data
        row = 1
        for asset in records:
            sheet.write(row, 0, asset.name or '', text_format)
            sheet.write(row, 1, asset.model_id.name or '', text_format)
            if asset.acquisition_date:
                sheet.write(row, 2, asset.acquisition_date or '', date_format)
            else:
                sheet.write(row, 2, '', text_format)
            sheet.write(row, 3, asset.original_value, num_format)
            sheet.write(row, 4, asset.value_residual, num_format)
            sheet.write(row, 5, asset.original_value - asset.value_residual, num_format)
            row += 1

        workbook.close()
        output.seek(0)
        return base64.b64encode(output.read())
