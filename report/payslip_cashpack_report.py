from odoo import models
import base64
import io
import zipfile


class HrPayslipRun(models.Model):
    _inherit = "hr.payslip.run"

    def action_print_cashpack_payslips(self):
        self.ensure_one()
        report = self.env.ref('mt_isy.action_report_payslip_cashpack', False)
        pdf_list = []
        serial = 1
        for slip in self.slip_ids:
            if slip.state not in ('draft', 'cancel'):
                # Render QWeb PDF for each payslip
                report = report.with_context(lang=slip.employee_id.sudo().address_id.lang)
                pdf_content, _ = report.sudo()._render_qweb_pdf(report, slip.id, data={'company_id': slip.company_id, 'serial': serial})
                pdf_list.append((f"{slip.employee_id.name}_payslip.pdf", pdf_content))
                serial += 1

        if not pdf_list:
            return

        # Multiple → bundle into ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for filename, pdf in pdf_list:
                zf.writestr(filename, pdf)
        zip_buffer.seek(0)

        attachment = self.env["ir.attachment"].create({
            "name": f"Cashpack_{self.name}_Payslips.zip",
            "datas": base64.b64encode(zip_buffer.read()),
            "mimetype": "application/zip",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }


class HrPays(models.Model):
    _inherit = "hr.payslip"

    def action_print_payslips(self):
        report = self.env.ref('mt_isy.action_report_payslip_cashpack', False)
        pdf_list = []
        serial = 1
        for slip in self:
            if slip.state not in ('draft', 'cancel'):
                # Render QWeb PDF for each payslip
                report = report.with_context(lang=slip.employee_id.sudo().address_id.lang)
                pdf_content, _ = report.sudo()._render_qweb_pdf(report, slip.id, data={'company_id': slip.company_id, 'serial': serial})
                pdf_list.append((f"{slip.employee_id.name}_payslip.pdf", pdf_content))
                serial += 1

        if not pdf_list:
            return

        # Multiple → bundle into ZIP
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w") as zf:
            for filename, pdf in pdf_list:
                zf.writestr(filename, pdf)
        zip_buffer.seek(0)

        attachment = self.env["ir.attachment"].create({
            "name": f"Cashpack_Payslips.zip",
            "datas": base64.b64encode(zip_buffer.read()),
            "mimetype": "application/zip",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

class ReportPayslipCashpack(models.AbstractModel):
    _name = "report.mt_isy.report_payslip_cashpack"
    _description = "Payslip Cashpack Report"

    def _get_report_values(self, docids, data=None):
        docs = self.env["hr.payslip"].browse(docids)

        # Example: get serial/index from data dict
        # You can pass 'serial' when calling _render_qweb_pdf
        serial = data.get('serial') if data else 0

        return {
            "doc_ids": docids,
            "doc_model": "hr.payslip",
            "docs": docs,
            "serial": serial,   # <-- now available in template
        }
