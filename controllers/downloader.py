from odoo import http
from odoo.http import request
import base64
from werkzeug.utils import secure_filename


def content_disposition(filename):
    """
    Creates a content disposition header for file downloads.
    """
    filename = secure_filename(filename)
    return f'attachment; filename="{filename}"'

class Binary(http.Controller):

    @http.route('/web/binary/download_document', type='http', auth="public")
    def download_document(self, model, field, id, filename=None, **kw):
        try:
            res = request.env[model].browse(int(id))
            filecontent = base64.b64decode(res.datas or '')

            if not filecontent:
                return request.not_found()

            if not filename:
                filename = f'{model.replace(".", "_")}_{id}'

            headers = [
                ('Content-Type', 'application/octet-stream'),
                ('Content-Disposition', content_disposition(filename)),
            ]

            return request.make_response(filecontent, headers=headers)
        except Exception as e:
            return request.make_response(f"Error: {str(e)}", [('Content-Type', 'text/plain')])
