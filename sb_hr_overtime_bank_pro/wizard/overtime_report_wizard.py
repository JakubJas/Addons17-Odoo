from odoo import models, fields
import base64
from io import BytesIO
from collections import defaultdict
from datetime import datetime, timedelta, time
import xlsxwriter
import pytz
import zipfile

class OvertimeReportWizard(models.TransientModel):

    report_type = fields.Selection([
        ('payroll', 'Gestoría'),
        ('employee', 'Trabajador'),
        ('attendance', 'Asistencia'),
    ], default=lambda self: self.env.context.get('report_type'))
    
    def action_generate(self):
        report_type = self.env.context.get('report_type')

        if report_type == 'employee':
            return self.action_export_employee_excel()

        elif report_type == 'attendance':
            return self.action_export_attendance_excel()

        else:
            return self.action_export_payroll_excel()
    
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

        # NOMBRE EMPRESA
        sheet.merge_range('A1:C1', company.name, title_format)

        # Fecha de exportación
        sheet.merge_range(
            'A2:C2',
            f'Fechas del reporte: {self.date_from.strftime("%d/%m/%Y")} - {self.date_to.strftime("%d/%m/%Y")}',
            center
        )

        # ENCABEZADOS
        start_row = 5

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

        if self.employee_id:
            return self._export_single_employee(self.employee_id)
        else:
            return self._export_all_employees_zip()

    def _generate_employee_excel(self, employee):
        company = self.env.company
        dni = employee.identification_id or ''

        attendances = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_in', '>=', fields.Datetime.to_datetime(self.date_from)),
            ('check_in', '<=', fields.Datetime.to_datetime(self.date_to)),
        ])

        attendances_total = self.env['hr.attendance'].search([
            ('employee_id', '=', employee.id),
            ('check_out', '!=', False),
        ])
        total_hours = sum(att.worked_hours for att in attendances_total)

        allocations = self.env['hr.leave.allocation'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.requires_allocation', '=', 'yes')
        ])
        total_allocated = sum(alloc.number_of_days for alloc in allocations)

        leaves_taken = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('holiday_status_id.requires_allocation', '=', 'yes')
        ])
        total_taken = sum(leave.number_of_days for leave in leaves_taken)

        remaining_leaves = total_allocated - total_taken

        overtime_records = self.env['hr.overtime.entry'].search([
            ('employee_id', '=', employee.id),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            ('state', '=', 'done'),
        ], order='date asc, id asc')

        total_extra = sum(r.hours for r in overtime_records if r.type == 'extra')
        total_payment = sum(abs(r.hours) for r in overtime_records if r.type == 'payment')
        total_compensation = sum(abs(r.hours) for r in overtime_records if r.type == 'compensation')
        total_adjustment = sum(r.hours for r in overtime_records if r.type == 'adjustment')
        total_worked = sum(attendances.mapped('worked_hours'))
        balance = sum(r._get_signed_hours() for r in overtime_records)

        all_entries = self.env['hr.overtime.entry'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'done'),
        ])
        total_balance = sum(r._get_signed_hours() for r in all_entries)

        leaves = self.env['hr.leave'].search([
            ('employee_id', '=', employee.id),
            ('state', '=', 'validate'),
            ('request_date_from', '<=', self.date_to),
            ('request_date_to', '>=', self.date_from),
        ], order='request_date_from asc')

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Resumen empleado')

        # FORMATOS
        company_fmt = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})
        header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D9EAD3', 'border': 1, 'align': 'center'})
        cell_fmt = workbook.add_format({'border': 1, 'align': 'center'})
        number_fmt = workbook.add_format({'border': 1, 'num_format': '0.00', 'align': 'center'})
        bold_fmt = workbook.add_format({'bold': True, 'align': 'center'})
        sign_fmt = workbook.add_format({'top': 1, 'align': 'center'})
        footer_fmt = workbook.add_format({'italic': True, 'align': 'center'})

        sheet.set_column('A:F', 30)

        row = 0

        sheet.merge_range(row, 0, row, 5, company.name, company_fmt)
        row += 1
        sheet.merge_range(row, 0, row, 5, 'Reporte detallado de horas extra', title_fmt)
        row += 2

        sheet.write(row, 0, 'Empleado', bold_fmt)
        sheet.write(row, 1, employee.name or 'N/A')
        sheet.write(row, 2, 'Días vacaciones', bold_fmt)
        sheet.write(row, 3, f"{remaining_leaves:.2f} / {total_allocated:.2f}", number_fmt)
        row += 1

        sheet.write(row, 0, 'DNI', bold_fmt)
        sheet.write(row, 1, dni)
        sheet.write(row, 2, 'Horas totales', bold_fmt)
        sheet.write_number(row, 3, total_hours, number_fmt)
        row += 1

        sheet.write(row, 0, 'Fecha desde', bold_fmt)
        sheet.write(row, 1, str(self.date_from))
        sheet.write(row, 2, 'Horas extra disponibles', bold_fmt)
        sheet.write_number(row, 3, total_balance, number_fmt)
        row += 1

        sheet.write(row, 0, 'Fecha hasta', bold_fmt)
        sheet.write(row, 1, str(self.date_to))
        row += 2

        sheet.merge_range(row, 0, row, 1, 'Resumen (mes)', header_fmt)
        row += 1

        sheet.write(row, 0, 'Horas extra', cell_fmt)
        sheet.write_number(row, 1, total_extra, number_fmt)
        row += 1

        sheet.write(row, 0, 'Pagadas', cell_fmt)
        sheet.write_number(row, 1, total_payment, number_fmt)
        row += 1

        sheet.write(row, 0, 'Compensadas', cell_fmt)
        sheet.write_number(row, 1, total_compensation, number_fmt)
        row += 1

        sheet.write(row, 0, 'Ajustes', cell_fmt)
        sheet.write_number(row, 1, total_adjustment, number_fmt)
        row += 1

        sheet.write(row, 0, 'Horas trabajadas mes', cell_fmt)
        sheet.write_number(row, 1, total_worked, number_fmt)
        row += 1

        sheet.write(row, 0, 'Saldo mes', cell_fmt)
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

        row += 2
        sheet.merge_range(row, 0, row, 5, 'Detalle de asistencias', header_fmt)
        row += 1

        headers = ['Fecha', 'Entrada', 'Salida', 'Horas']
        for col, h in enumerate(headers):
            sheet.write(row, col, h, header_fmt)
        row += 1

        for att in attendances:
            sheet.write(row, 0, att.check_in.strftime('%d/%m/%Y') if att.check_in else '', cell_fmt)
            sheet.write(row, 1, att.check_in.strftime('%H:%M') if att.check_in else '', cell_fmt)
            sheet.write(row, 2, att.check_out.strftime('%H:%M') if att.check_out else '', cell_fmt)
            sheet.write_number(row, 3, att.worked_hours or 0.0, number_fmt)
            row += 1

        row += 2
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

        sheet.merge_range(
            row, 0, row, 5,
            f'Creado por Overtime Bank Pro - {datetime.now().year}',
            footer_fmt
        )

        workbook.close()
        output.seek(0)

        return output

    def _export_single_employee(self, employee):
        output = self._generate_employee_excel(employee)

        attachment = self.env['ir.attachment'].create({
            'name': f'reporte_{employee.name}.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    def _export_all_employees_zip(self):
        employees = self.env['hr.employee'].search([])

        zip_buffer = BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
            for employee in employees:
                output = self._generate_employee_excel(employee)
                filename = f"{employee.name.replace(' ', '_')}.xlsx"
                zip_file.writestr(filename, output.getvalue())

        zip_buffer.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'reportes_empleados.zip',
            'type': 'binary',
            'datas': base64.b64encode(zip_buffer.read()),
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }
        
    def _get_expected_hours(self, employee, date):
        calendar = employee.resource_calendar_id

        if not calendar or not employee.resource_id:
            return 0.0

        tz = pytz.timezone(self.env.user.tz or 'UTC')

        start = tz.localize(datetime.combine(date, time.min))
        end = tz.localize(datetime.combine(date, time.max))

        intervals = calendar._work_intervals_batch(
            start, end, resources=employee.resource_id
        )

        total = 0.0
        for interval in intervals.get(employee.resource_id.id, []):
            duration = (interval[1] - interval[0]).total_seconds() / 3600
            total += duration

        return total

    def action_export_attendance_excel(self):

        employees = self.env['hr.employee'].search([])

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet('Asistencia')

        header = workbook.add_format({'bold': True, 'border': 1, 'align': 'center'})
        normal = workbook.add_format()
        bold_center = workbook.add_format({'bold': True, 'align': 'center'})
        footer_format = workbook.add_format({'italic': True, 'align': 'center'})
        
        green = workbook.add_format({'bg_color': '#C6EFCE', 'border': 1, 'align': 'center'})
        yellow = workbook.add_format({'bg_color': '#FFEB9C', 'border': 1, 'align': 'center'})
        red = workbook.add_format({'bg_color': '#FFC7CE', 'border': 1, 'align': 'center'})
        grey = workbook.add_format({'bg_color': '#D9D9D9', 'border': 1, 'align': 'center'})

        title_format = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
        subtitle_format = workbook.add_format({'bold': True, 'align': 'left'})

        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 100, 10)
        sheet.freeze_panes(3, 1)

        sheet.merge_range(
            0, 0, 0, 6,
            f'Reporte de Asistencia ({self.date_from} - {self.date_to})',
            title_format
        )

        sheet.write(1, 0, 'Leyenda:', subtitle_format)
        sheet.write(1, 1, 'Correcto', green)
        sheet.write(1, 2, 'Incompleto', yellow)
        sheet.write(1, 3, 'No fichó', red)
        sheet.write(1, 4, 'Vacaciones', grey)

        start_row = 3
        sheet.write(start_row, 0, 'Empleado', header)

        col = 1
        dates = []
        current_date = self.date_from

        while current_date <= self.date_to:
            sheet.write(start_row, col, current_date.strftime('%d/%m'), header)
            dates.append(current_date)
            col += 1
            current_date += timedelta(days=1)

        row = start_row + 1

        for employee in employees:

            sheet.write(row, 0, employee.name or '', normal)

            col = 1

            for date in dates:

                # HORAS TRABAJADAS
                attendances = self.env['hr.attendance'].search([
                    ('employee_id', '=', employee.id),
                    ('check_in', '>=', str(date) + ' 00:00:00'),
                    ('check_in', '<=', str(date) + ' 23:59:59'),
                ])

                worked_hours = sum(attendances.mapped('worked_hours'))

                # HORAS ESPERADAS
                expected_hours = self._get_expected_hours(employee, date)

                # VACACIONES
                leave = self.env['hr.leave'].search([
                    ('employee_id', '=', employee.id),
                    ('state', '=', 'validate'),
                    ('request_date_from', '<=', date),
                    ('request_date_to', '>=', date),
                ], limit=1)

                # LÓGICA COLORES
                if leave:
                    fmt = grey
                    value = 'V'

                elif expected_hours == 0:
                    fmt = grey
                    value = ''

                elif worked_hours == 0:
                    fmt = red
                    value = 0

                elif worked_hours < expected_hours:
                    fmt = yellow
                    value = round(worked_hours, 2)

                else:
                    fmt = green
                    value = round(worked_hours, 2)

                sheet.write(row, col, value, fmt)
                col += 1

            row += 1

        sheet.merge_range(row + 2, 0, row + 2, 6, f'Creado por Overtime Bank Pro - Servi Byte Canarias SL - {datetime.now().year}', footer_format)

        workbook.close()
        output.seek(0)

        attachment = self.env['ir.attachment'].create({
            'name': 'reporte_asistencia.xlsx',
            'type': 'binary',
            'datas': base64.b64encode(output.read()),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }