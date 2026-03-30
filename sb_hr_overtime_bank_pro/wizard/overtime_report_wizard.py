from odoo import models, fields
import base64
from io import BytesIO
from collections import defaultdict
from datetime import datetime
import xlsxwriter

class OvertimeReportWizard(models.TransientModel):
    _name = 'overtime.report.wizard'
    _description = 'Overtime Report Wizard'

    date_from = fields.Date(required=True, string="Fecha desde")
    date_to = fields.Date(required=True, string="Fecha hasta")
    employee_id = fields.Many2one('hr.employee', string="Empleado")
    
    def action_export_payroll_excel(self):
        self.ensure_one()

        company = self.env.company 

        domain = [
            ('type', '=', 'payment'),
            ('state', '=', 'done'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ]

        records = self.env['hr.overtime.entry'].search(domain)

        # Agrupar por empleado
        data = {}
        for rec in records:
            name = rec.employee_id.name
            if name not in data:
                data[name] = {
                    'hours': 0,
                    'dni': rec.employee_id.identification_id
                }
            data[name]['hours'] += rec.hours

        # Crear Excel
        import xlsxwriter

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Gestoria')

        bold = workbook.add_format({'bold': True})
        center = workbook.add_format({'align': 'center'})
        header = workbook.add_format({'bold': True, 'align': 'center'})
        cell = workbook.add_format({'border': 1})
        footer_format = workbook.add_format({'italic': True, 'align': 'center'})
        title_format = workbook.add_format({'align': 'center', 'font_size': 14})
        combo_format = workbook.add_format({'align': 'center', 'border': 1})

        # Ajustar columnas
        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 20)
        sheet.set_column('C:C', 20)

        # LOGO
        # Ajustar tamaño de fila y columna para "encajar" el logo
        # sheet.set_row(0, 60)        # altura fila A1
        # sheet.set_column('A:A', 25) # ancho columna A

        # if company.logo:
        #     image_data = BytesIO(base64.b64decode(company.logo))
        #     sheet.insert_image('A1', 'logo.png', {
        #         'image_data': image_data,
        #         'x_scale': 0.5,
        #         'y_scale': 0.5,
        #         'x_offset': 5,
        #         'y_offset': 5,
        #         'object_position': 1 
        #     })

        # NOMBRE EMPRESA
        sheet.merge_range('A1:C1', company.name, title_format)

        # Fecha de exportación
        sheet.merge_range(
            'A2:C2',
            f'Fechas del reporte: {self.date_from.strftime("%d/%m/%Y")} - {self.date_to.strftime("%d/%m/%Y")}',
            center
        )

        # ENCABEZADOS
        start_row = 4

        sheet.write(start_row, 0, 'Empleado', header)
        sheet.write(start_row, 1, 'DNI', header)
        sheet.write(start_row, 2, 'Horas a pagar', header)

        # DATOS
        row = start_row + 1

        for employee, vals in data.items():
            sheet.write(row, 0, employee, combo_format)
            sheet.write(row, 1, vals['dni'], combo_format)
            sheet.write(row, 2, vals['hours'], combo_format)
            row += 1

        # FOOTER
        sheet.merge_range(
            row + 2, 0, row + 2, 2,
            f'Creado por Overtime Bank Pro - Servi Byte Canarias SL - {datetime.now().year}',
            footer_format
        )

        workbook.close()
        output.seek(0)

        file_data = base64.b64encode(output.read())

        attachment = self.env['ir.attachment'].create({
            'name': f'reporte_gestoria_{datetime.now().strftime("%Y%m%d")}.xlsx',
            'type': 'binary',
            'datas': file_data,
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
        
    def action_export_employee_excel(self):
        self.ensure_one()
        
        company = self.env.company 

        if not self.employee_id:
            raise ValueError("Debes seleccionar un empleado.")

        employee = self.employee_id or self.env['hr.employee'].search([])

        overtime_domain = [
            ('employee_id', '=', employee.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'done'),
        ]
        overtime_records = self.env['hr.overtime.entry'].search(overtime_domain, order='date asc, id asc')

        attendance_domain = [
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('check_in', '<=', fields.Datetime.to_datetime(self.date_to)),
        ]
        attendances = self.env['hr.attendance'].search(attendance_domain)

        leave_domain = [
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', self.date_to),
            ('request_date_to', '>=', self.date_from),
        ]
        leaves = self.env['hr.leave'].search(leave_domain, order='request_date_from asc')

        total_extra = sum(r.hours for r in overtime_records if r.type == 'extra')
        total_payment = sum(abs(r.hours) for r in overtime_records if r.type == 'payment')
        total_compensation = sum(abs(r.hours) for r in overtime_records if r.type == 'compensation')
        total_adjustment = sum(r.hours for r in overtime_records if r.type == 'adjustment')
        total_worked = sum(attendances.mapped('worked_hours'))
        balance = sum(r._get_signed_hours() for r in overtime_records)

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Resumen empleado')

        company_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1, 'align': 'center'})
        number_fmt = workbook.add_format({'border': 1, 'num_format': '0.00', 'align': 'center'})
        bold_fmt = workbook.add_format({'bold': True, 'align': 'center'})
        sign_fmt = workbook.add_format({'top': 1, 'align': 'center'})
        footer_fmt = workbook.add_format({'italic': True, 'align': 'center'})

        sheet.set_column('A:A', 30)
        sheet.set_column('B:B', 30)
        sheet.set_column('C:C', 18)
        sheet.set_column('D:D', 30)
        sheet.set_column('E:E', 30)
        sheet.set_column('F:F', 30)

        row = 0
        # NOMBRE EMPRESA
        sheet.merge_range(row, 0, row, 5, company.name, company_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 1, 'Reporte detallado de horas extra', title_fmt)
        row += 2

        sheet.write(row, 0, 'Empleado', bold_fmt)
        sheet.write(row, 1, employee.name or 'Empleado sin nombre')
        row += 1
        sheet.write(row, 0, 'Fecha desde', bold_fmt)
        sheet.write(row, 1, str(self.date_from))
        row += 1
        sheet.write(row, 0, 'Fecha hasta', bold_fmt)
        sheet.write(row, 1, str(self.date_to))
        row += 2

        sheet.merge_range(row, 0, row, 1, 'Resumen', header_fmt)
        row += 1
        sheet.write(row, 0, 'Horas extra generadas', cell_fmt)
        sheet.write_number(row, 1, total_extra, number_fmt)
        row += 1
        sheet.write(row, 0, 'Horas pagadas', cell_fmt)
        sheet.write_number(row, 1, total_payment, number_fmt)
        row += 1
        sheet.write(row, 0, 'Horas compensadas', cell_fmt)
        sheet.write_number(row, 1, total_compensation, number_fmt)
        row += 1
        sheet.write(row, 0, 'Ajustes manuales', cell_fmt)
        sheet.write_number(row, 1, total_adjustment, number_fmt)
        row += 1
        sheet.write(row, 0, 'Horas laborales totales', cell_fmt)
        sheet.write_number(row, 1, total_worked, number_fmt)
        row += 1
        sheet.write(row, 0, 'Saldo final banco', cell_fmt)
        sheet.write_number(row, 1, balance, number_fmt)
        row += 2

        sheet.merge_range(row, 0, row, 5, 'Detalle de movimientos', header_fmt)
        row += 1
        headers = ['Fecha', 'Tipo', 'Horas', 'Referencia', 'Descripción', 'Estado']
        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_fmt)
        row += 1

        type_labels = dict(self.env['hr.overtime.entry']._fields['type'].selection)
        state_labels = dict(self.env['hr.overtime.entry']._fields['state'].selection)

        for rec in overtime_records:
            sheet.write(row, 0, str(rec.date or ''), cell_fmt)
            sheet.write(row, 1, type_labels.get(rec.type, rec.type or ''), cell_fmt)
            sheet.write_number(row, 2, rec.hours or 0.0, number_fmt)
            sheet.write(row, 3, rec.reference or '', cell_fmt)
            sheet.write(row, 4, rec.description or '', cell_fmt)
            sheet.write(row, 5, state_labels.get(rec.state, rec.state or ''), cell_fmt)
            row += 1

        row += 1
        sheet.merge_range(row, 0, row, 4, 'Días libres utilizados', header_fmt)
        row += 1

        leave_headers = ['Desde', 'Hasta', 'Días', 'Tipo ausencia', 'Descripción']
        for col, header in enumerate(leave_headers):
            sheet.write(row, col, header, header_fmt)
        row += 1

        for leave in leaves:
            sheet.write(row, 0, str(leave.request_date_from or ''), cell_fmt)
            sheet.write(row, 1, str(leave.request_date_to or ''), cell_fmt)
            sheet.write_number(row, 2, leave.number_of_days or 0.0, number_fmt)
            sheet.write(row, 3, leave.holiday_status_id.name or '', cell_fmt)
            sheet.write(row, 4, leave.name or '', cell_fmt)
            row += 1

        row += 3
        sheet.write(row, 1, 'Firma empleado', sign_fmt)
        sheet.write(row, 4, 'Firma empresa', sign_fmt)
        row += 2
        
        sheet.merge_range(row, 0, row, 5, f'Creado por Overtime Bank Pro - Servi Byte Canarias SL - {datetime.now().year}', footer_fmt)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': f'reporte_empleado_{employee.name}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }