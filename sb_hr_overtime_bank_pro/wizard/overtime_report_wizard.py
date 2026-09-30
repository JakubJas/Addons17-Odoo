from odoo import models, fields
import base64
from io import BytesIO
from collections import defaultdict
from datetime import datetime, timedelta, time, date
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
            sheet.write(row, 2, self._format_hours(abs(vals['hours'])), combo_format)
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

    def _get_employee_vacation_balance_until(self, employee, date_to):
        
        Allocation = self.env["hr.leave.allocation"]
        Leave = self.env["hr.leave"]

        allocation_domain = [
            ("employee_id", "=", employee.id),
            ("state", "=", "validate"),
            ("holiday_status_id.requires_allocation", "=", "yes"),
        ]

        if "date_from" in Allocation._fields:
            allocation_domain += [
                "|",
                ("date_from", "=", False),
                ("date_from", "<=", date_to),
            ]

        allocations = Allocation.search(allocation_domain)

        accrued_days = 0.0
        leave_type_ids = set()

        for allocation in allocations:
            leave_type_ids.add(allocation.holiday_status_id.id)

            allocated_days = allocation.number_of_days or 0.0

            allocation_start = (
                allocation.date_from
                if "date_from" in allocation._fields and allocation.date_from
                else date(date_to.year, 1, 1)
            )

            allocation_end = (
                allocation.date_to
                if "date_to" in allocation._fields and allocation.date_to
                else date(allocation_start.year, 12, 31)
            )

            if allocation_start > date_to:
                continue

            effective_end = min(date_to, allocation_end)

            # Número total de meses cubiertos por la asignación.
            total_months = (
                (allocation_end.year - allocation_start.year) * 12
                + allocation_end.month
                - allocation_start.month
                + 1
            )

            # Meses generados hasta la fecha final del informe.
            accrued_months = (
                (effective_end.year - allocation_start.year) * 12
                + effective_end.month
                - allocation_start.month
                + 1
            )

            if total_months <= 0:
                continue

            accrued_months = min(accrued_months, total_months)

            accrued_days += (
                allocated_days
                * accrued_months
                / total_months
            )

        if not leave_type_ids:
            return {
                "allocated": 0.0,
                "used": 0.0,
                "remaining": 0.0,
            }

        leaves = Leave.search([
            ("employee_id", "=", employee.id),
            ("state", "=", "validate"),
            ("holiday_status_id", "in", list(leave_type_ids)),
            ("request_date_from", "<=", date_to),
        ])

        used_days = 0.0

        for leave in leaves:
            if not leave.request_date_from:
                continue

            if leave.request_date_from > date_to:
                continue

            # Si la ausencia termina dentro del periodo, se toma completa.
            if (
                not leave.request_date_to
                or leave.request_date_to <= date_to
            ):
                used_days += leave.number_of_days or 0.0
                continue

            # Si atraviesa date_to, se contabiliza solo la parte correspondiente.
            total_span = (
                leave.request_date_to - leave.request_date_from
            ).days + 1

            used_span = (
                date_to - leave.request_date_from
            ).days + 1

            if total_span > 0 and used_span > 0:
                used_days += (
                    (leave.number_of_days or 0.0)
                    * used_span
                    / total_span
                )

        remaining_days = accrued_days - used_days

        return {
            "allocated": accrued_days,
            "used": used_days,
            "remaining": remaining_days,
        }
        
    def _format_hours(self, decimal_hours):
        
        decimal_hours = decimal_hours or 0.0

        is_negative = decimal_hours < 0
        total_minutes = round(abs(decimal_hours) * 60)

        hours, minutes = divmod(total_minutes, 60)

        result = f"{hours:02d}:{minutes:02d}"

        if is_negative:
            result = f"-{result}"

        return result
    
    def _generate_employee_excel(self, employee):
        company = self.env.company
        dni = employee.identification_id or ""

        year_start = date(self.date_to.year, 1, 1)

        period_start = datetime.combine(self.date_from, time.min)
        period_end = datetime.combine(self.date_to, time.max)

        accumulated_start = datetime.combine(year_start, time.min)
        accumulated_end = datetime.combine(self.date_to, time.max)

        # Asistencias del periodo seleccionado.
        attendances = self.env["hr.attendance"].search([
            ("employee_id", "=", employee.id),
            ("check_in", ">=", fields.Datetime.to_string(period_start)),
            ("check_in", "<=", fields.Datetime.to_string(period_end)),
        ], order="check_in asc")

        # Asistencias acumuladas desde enero hasta date_to.
        accumulated_attendances = self.env["hr.attendance"].search([
            ("employee_id", "=", employee.id),
            ("check_in", ">=", fields.Datetime.to_string(accumulated_start)),
            ("check_in", "<=", fields.Datetime.to_string(accumulated_end)),
            ("check_out", "!=", False),
        ])

        total_hours_accumulated = sum(
            accumulated_attendances.mapped("worked_hours")
        )

        # Vacaciones acumuladas según las asignaciones reales de Odoo.
        vacation_balance = self._get_employee_vacation_balance_until(
            employee,
            self.date_to,
        )

        vacation_allocated = vacation_balance["allocated"]
        vacation_used = vacation_balance["used"]
        vacation_remaining = vacation_balance["remaining"]

        # Movimientos del periodo seleccionado.
        overtime_records = self.env["hr.overtime.entry"].search([
            ("employee_id", "=", employee.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("state", "=", "done"),
        ], order="date asc, id asc")

        total_extra = sum(
            r._get_signed_hours()
            for r in overtime_records
            if r.type == "extra"
        )

        total_payment = sum(
            abs(r._get_signed_hours())
            for r in overtime_records
            if r.type == "payment"
        )

        total_compensation = sum(
            abs(r._get_signed_hours())
            for r in overtime_records
            if r.type == "compensation"
        )

        total_early_exit = sum(
            abs(r._get_signed_hours())
            for r in overtime_records
            if r.type == "early_exit"
        )

        total_adjustment = sum(
            r._get_signed_hours()
            for r in overtime_records
            if r.type == "adjustment"
        )

        total_worked_period = sum(
            attendances.mapped("worked_hours")
        )

        period_balance = sum(
            r._get_signed_hours()
            for r in overtime_records
        )

        # Saldo acumulado solamente hasta date_to.
        accumulated_entries = self.env["hr.overtime.entry"].search([
            ("employee_id", "=", employee.id),
            ("date", "<=", self.date_to),
            ("state", "=", "done"),
        ])

        total_balance_accumulated = sum(
            r._get_signed_hours()
            for r in accumulated_entries
        )

        # Ausencias del periodo seleccionado.
        leaves = self.env["hr.leave"].search([
            ("employee_id", "=", employee.id),
            ("state", "=", "validate"),
            ("request_date_from", "<=", self.date_to),
            ("request_date_to", ">=", self.date_from),
        ], order="request_date_from asc")

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet("Resumen empleado")

        # FORMATOS
        company_fmt = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "align": "center",
        })

        title_fmt = workbook.add_format({
            "bold": True,
            "font_size": 14,
            "align": "center",
        })

        header_fmt = workbook.add_format({
            "bold": True,
            "bg_color": "#D9EAD3",
            "border": 1,
            "align": "center",
        })

        cell_fmt = workbook.add_format({
            "border": 1,
            "align": "center",
        })

        number_fmt = workbook.add_format({
            "border": 1,
            "num_format": "0.00",
            "align": "center",
        })

        bold_fmt = workbook.add_format({
            "bold": True,
            "align": "center",
        })

        sign_fmt = workbook.add_format({
            "top": 1,
            "align": "center",
        })

        footer_fmt = workbook.add_format({
            "italic": True,
            "align": "center",
        })

        sheet.set_column("A:A", 27)
        sheet.set_column("B:B", 22)
        sheet.set_column("C:C", 34)
        sheet.set_column("D:D", 24)
        sheet.set_column("E:E", 35)
        sheet.set_column("F:F", 20)

        row = 0

        sheet.merge_range(row, 0, row, 5, company.name, company_fmt)
        row += 1

        sheet.merge_range(
            row,
            0,
            row,
            5,
            "Reporte detallado de horas extra",
            title_fmt,
        )
        row += 2

        sheet.write(row, 0, "Empleado", bold_fmt)
        sheet.write(row, 1, employee.name or "N/A")

        sheet.write(
            row,
            2,
            "Vacaciones disponibles / generadas",
            bold_fmt,
        )

        sheet.write(
            row,
            3,
            f"{vacation_remaining:.2f} / {vacation_allocated:.2f}",
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "DNI", bold_fmt)
        sheet.write(row, 1, dni)

        sheet.write(
            row,
            2,
            "Vacaciones utilizadas",
            bold_fmt,
        )

        sheet.write(
            row,
            3,
            round(vacation_used, 2),
            number_fmt,
        )
        row += 1

        sheet.write(row, 0, "Fecha desde", bold_fmt)
        sheet.write(row, 1, self.date_from.strftime("%d/%m/%Y"))

        sheet.write(
            row,
            2,
            "Horas trabajadas acumuladas",
            bold_fmt,
        )

        sheet.write(
            row,
            3,
            self._format_hours(total_hours_accumulated),
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "Fecha hasta", bold_fmt)
        sheet.write(row, 1, self.date_to.strftime("%d/%m/%Y"))

        sheet.write(
            row,
            2,
            "Saldo horas extra hasta la fecha",
            bold_fmt,
        )

        sheet.write(
            row,
            3,
            self._format_hours(total_balance_accumulated),
            cell_fmt,
        )
        row += 2

        # RESUMEN DEL PERIODO
        sheet.merge_range(
            row,
            0,
            row,
            1,
            "Resumen del periodo",
            header_fmt,
        )
        row += 1

        sheet.write(row, 0, "Horas extra generadas", cell_fmt)
        sheet.write(row, 1, self._format_hours(total_extra), cell_fmt)
        row += 1

        sheet.write(row, 0, "Horas pagadas", cell_fmt)
        sheet.write(row, 1, self._format_hours(total_payment), cell_fmt)
        row += 1

        sheet.write(row, 0, "Horas compensadas", cell_fmt)
        sheet.write(
            row,
            1,
            self._format_hours(total_compensation),
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "Salidas tempranas", cell_fmt)
        sheet.write(
            row,
            1,
            self._format_hours(total_early_exit),
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "Ajustes", cell_fmt)
        sheet.write(
            row,
            1,
            self._format_hours(total_adjustment),
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "Horas trabajadas periodo", cell_fmt)
        sheet.write(
            row,
            1,
            self._format_hours(total_worked_period),
            cell_fmt,
        )
        row += 1

        sheet.write(row, 0, "Saldo del periodo", cell_fmt)
        sheet.write(
            row,
            1,
            self._format_hours(period_balance),
            cell_fmt,
        )
        row += 2

        # DETALLE DE MOVIMIENTOS
        sheet.merge_range(
            row,
            0,
            row,
            5,
            "Detalle de movimientos",
            header_fmt,
        )
        row += 1

        headers = [
            "Fecha",
            "Tipo",
            "Horas",
            "Referencia",
            "Descripción",
            "Estado",
        ]

        for col, header in enumerate(headers):
            sheet.write(row, col, header, header_fmt)

        row += 1

        type_field = self.env["hr.overtime.entry"]._fields["type"]
        state_field = self.env["hr.overtime.entry"]._fields["state"]

        type_labels = dict(
            type_field._description_selection(self.env)
        )

        state_labels = dict(
            state_field._description_selection(self.env)
        )

        for rec in overtime_records:
            signed_hours = rec._get_signed_hours()

            sheet.write(
                row,
                0,
                rec.date.strftime("%d/%m/%Y") if rec.date else "",
                cell_fmt,
            )

            sheet.write(
                row,
                1,
                type_labels.get(rec.type, rec.type or ""),
                cell_fmt,
            )

            sheet.write(
                row,
                2,
                self._format_hours(signed_hours),
                cell_fmt,
            )

            sheet.write(
                row,
                3,
                rec.reference or "",
                cell_fmt,
            )

            sheet.write(
                row,
                4,
                rec.description or "",
                cell_fmt,
            )

            sheet.write(
                row,
                5,
                state_labels.get(rec.state, rec.state or ""),
                cell_fmt,
            )

            row += 1

        # DETALLE DE ASISTENCIAS
        row += 2

        sheet.merge_range(
            row,
            0,
            row,
            5,
            "Detalle de asistencias",
            header_fmt,
        )
        row += 1

        attendance_headers = [
            "Fecha",
            "Entrada",
            "Salida",
            "Horas",
        ]

        for col, header in enumerate(attendance_headers):
            sheet.write(row, col, header, header_fmt)

        row += 1

        employee_tz = pytz.timezone(
            employee.resource_calendar_id.tz
            or self.env.user.tz
            or "UTC"
        )

        for attendance in attendances:
            check_in_local = False
            check_out_local = False

            if attendance.check_in:
                check_in_utc = pytz.UTC.localize(attendance.check_in)
                check_in_local = check_in_utc.astimezone(employee_tz)

            if attendance.check_out:
                check_out_utc = pytz.UTC.localize(attendance.check_out)
                check_out_local = check_out_utc.astimezone(employee_tz)

            sheet.write(
                row,
                0,
                check_in_local.strftime("%d/%m/%Y")
                if check_in_local else "",
                cell_fmt,
            )

            sheet.write(
                row,
                1,
                check_in_local.strftime("%H:%M")
                if check_in_local else "",
                cell_fmt,
            )

            sheet.write(
                row,
                2,
                check_out_local.strftime("%H:%M")
                if check_out_local else "",
                cell_fmt,
            )

            sheet.write(
                row,
                3,
                self._format_hours(attendance.worked_hours),
                cell_fmt,
            )

            row += 1

        # AUSENCIAS
        row += 2

        sheet.merge_range(
            row,
            0,
            row,
            4,
            "Días libres utilizados",
            header_fmt,
        )
        row += 1

        leave_headers = [
            "Desde",
            "Hasta",
            "Días",
            "Tipo ausencia",
            "Descripción",
        ]

        for col, header in enumerate(leave_headers):
            sheet.write(row, col, header, header_fmt)

        row += 1

        for leave in leaves:
            sheet.write(
                row,
                0,
                leave.request_date_from.strftime("%d/%m/%Y")
                if leave.request_date_from else "",
                cell_fmt,
            )

            sheet.write(
                row,
                1,
                leave.request_date_to.strftime("%d/%m/%Y")
                if leave.request_date_to else "",
                cell_fmt,
            )

            sheet.write(
                row,
                2,
                leave.number_of_days or 0.0,
                number_fmt,
            )

            sheet.write(
                row,
                3,
                leave.holiday_status_id.name or "",
                cell_fmt,
            )

            sheet.write(
                row,
                4,
                leave.name or "",
                cell_fmt,
            )

            row += 1

        row += 3

        sheet.write(row, 1, "Firma empleado", sign_fmt)
        sheet.write(row, 4, "Firma empresa", sign_fmt)
        row += 2

        sheet.merge_range(
            row,
            0,
            row,
            5,
            f"Creado por Overtime Bank Pro - {datetime.now().year}",
            footer_fmt,
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
        
    def _get_employee_timezone(self, employee):
        timezone_name = (
            employee.resource_calendar_id.tz
            if employee.resource_calendar_id and employee.resource_calendar_id.tz
            else self.env.user.tz or "UTC"
        )
        return pytz.timezone(timezone_name)

    def _get_utc_day_range(self, employee, day):
        timezone = self._get_employee_timezone(employee)

        local_start = timezone.localize(
            datetime.combine(day, time.min)
        )
        local_end = timezone.localize(
            datetime.combine(day + timedelta(days=1), time.min)
        )

        utc_start = local_start.astimezone(pytz.UTC).replace(tzinfo=None)
        utc_end = local_end.astimezone(pytz.UTC).replace(tzinfo=None)

        return utc_start, utc_end

    def _get_expected_hours(self, employee, day):
        """Horas previstas del día usando el mismo motor que Asistencias."""
        return self.env["hr.attendance"]._get_expected_hours_for_day(
            employee,
            day,
        )

    def _get_worked_hours(self, employee, day):
        """Horas fichadas del día respetando la zona horaria del empleado."""
        return self.env["hr.attendance"]._get_worked_hours_for_day(
            employee,
            day,
        )

    def _get_attendance_summary(self, employee):
        """
        Resumen del periodo.

        Las horas extra, salidas, pagos, descansos y ajustes se leen de
        hr.overtime.entry. No se recalculan en el Excel, por lo que el resumen
        coincide con Overtime Bank y respeta cálculo diario/semanal flexible.
        """
        OvertimeEntry = self.env["hr.overtime.entry"]
        Attendance = self.env["hr.attendance"]

        entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
            ("state", "=", "done"),
        ])

        accumulated_entries = OvertimeEntry.search([
            ("employee_id", "=", employee.id),
            ("date", "<=", self.date_to),
            ("state", "=", "done"),
        ])

        worked = 0.0
        expected = 0.0
        current = self.date_from

        while current <= self.date_to:
            worked += Attendance._get_worked_hours_for_day(employee, current)
            expected += Attendance._get_expected_hours_for_day(employee, current)
            current += timedelta(days=1)

        def signed_for(entry_type):
            return sum(
                entry._get_signed_hours()
                for entry in entries
                if entry.type == entry_type
            )

        return {
            "worked": worked,
            "expected": expected,
            "extra": max(signed_for("extra"), 0.0),
            "early_exit": abs(signed_for("early_exit")),
            "payment": abs(signed_for("payment")),
            "compensation": abs(signed_for("compensation")),
            "adjustment": signed_for("adjustment"),
            "period_balance": sum(
                entry._get_signed_hours() for entry in entries
            ),
            "balance": sum(
                entry._get_signed_hours()
                for entry in accumulated_entries
            ),
        }

    def action_export_attendance_excel(self):
        self.ensure_one()

        employees = self.env["hr.employee"].search([], order="name asc")
        Attendance = self.env["hr.attendance"]
        Leave = self.env["hr.leave"]

        output = BytesIO()
        workbook = xlsxwriter.Workbook(output)
        sheet = workbook.add_worksheet("Asistencia")

        header = workbook.add_format({
            "bold": True,
            "border": 1,
            "align": "center",
            "valign": "vcenter",
            "bg_color": "#D9EAD3",
        })
        normal = workbook.add_format({"valign": "vcenter"})
        footer_format = workbook.add_format({
            "italic": True,
            "align": "center",
        })
        title_format = workbook.add_format({
            "bold": True,
            "font_size": 16,
            "align": "center",
        })
        subtitle_format = workbook.add_format({
            "bold": True,
            "align": "left",
        })
        summary_title = workbook.add_format({
            "bold": True,
            "font_size": 13,
            "align": "left",
            "bg_color": "#D9EAD3",
        })
        summary_cell = workbook.add_format({
            "border": 1,
            "align": "center",
        })
        green = workbook.add_format({
            "bg_color": "#C6EFCE",
            "border": 1,
            "align": "center",
        })
        yellow = workbook.add_format({
            "bg_color": "#FFEB9C",
            "border": 1,
            "align": "center",
        })
        red = workbook.add_format({
            "bg_color": "#FFC7CE",
            "border": 1,
            "align": "center",
        })
        grey = workbook.add_format({
            "bg_color": "#D9D9D9",
            "border": 1,
            "align": "center",
        })

        # ---------------------------------------------------------
        # RESUMEN POR EMPLEADO
        # ---------------------------------------------------------
        sheet.set_column("A:A", 30)
        sheet.set_column("B:I", 18)

        sheet.merge_range(
            0, 0, 0, 8,
            f"Reporte de Asistencia ({self.date_from.strftime('%d/%m/%Y')} - {self.date_to.strftime('%d/%m/%Y')})",
            title_format,
        )

        sheet.merge_range(2, 0, 2, 8, "Resumen por empleado", summary_title)

        summary_headers = [
            "Empleado",
            "Horas trabajadas",
            "Horas previstas",
            "Horas extra generadas",
            "Salidas tempranas",
            "Pagadas en nómina",
            "Descansos compensados",
            "Ajustes",
            "Saldo Overtime",
        ]

        for col, label in enumerate(summary_headers):
            sheet.write(3, col, label, header)

        summary_row = 4
        for employee in employees:
            values = self._get_attendance_summary(employee)

            sheet.write(summary_row, 0, employee.name or "", summary_cell)
            sheet.write(summary_row, 1, self._format_hours(values["worked"]), summary_cell)
            sheet.write(summary_row, 2, self._format_hours(values["expected"]), summary_cell)
            sheet.write(summary_row, 3, self._format_hours(values["extra"]), summary_cell)
            sheet.write(summary_row, 4, self._format_hours(values["early_exit"]), summary_cell)
            sheet.write(summary_row, 5, self._format_hours(values["payment"]), summary_cell)
            sheet.write(summary_row, 6, self._format_hours(values["compensation"]), summary_cell)
            sheet.write(summary_row, 7, self._format_hours(values["adjustment"]), summary_cell)
            sheet.write(summary_row, 8, self._format_hours(values["balance"]), summary_cell)
            summary_row += 1

        # ---------------------------------------------------------
        # DETALLE DIARIO
        # ---------------------------------------------------------
        detail_title_row = summary_row + 2
        sheet.merge_range(
            detail_title_row, 0, detail_title_row, 8,
            "Detalle diario de asistencia",
            summary_title,
        )

        legend_row = detail_title_row + 1
        sheet.write(legend_row, 0, "Leyenda:", subtitle_format)
        sheet.write(legend_row, 1, "Correcto", green)
        sheet.write(legend_row, 2, "Incompleto", yellow)
        sheet.write(legend_row, 3, "No fichó", red)
        sheet.write(legend_row, 4, "Ausencia", grey)

        start_row = detail_title_row + 3
        sheet.write(start_row, 0, "Empleado", header)

        dates = []
        current_date = self.date_from
        col = 1

        while current_date <= self.date_to:
            sheet.write(start_row, col, current_date.strftime("%d/%m"), header)
            dates.append(current_date)
            current_date += timedelta(days=1)
            col += 1

        # Las columnas del detalle pueden superar I.
        sheet.set_column(1, max(1, len(dates)), 10)
        sheet.freeze_panes(start_row + 1, 1)

        row = start_row + 1

        for employee in employees:
            sheet.write(row, 0, employee.name or "", normal)

            col = 1
            for day in dates:
                worked_hours = Attendance._get_worked_hours_for_day(
                    employee,
                    day,
                )
                expected_hours = Attendance._get_expected_hours_for_day(
                    employee,
                    day,
                )

                leave = Leave.search([
                    ("employee_id", "=", employee.id),
                    ("state", "=", "validate"),
                    ("request_date_from", "<=", day),
                    ("request_date_to", ">=", day),
                ], limit=1)

                if leave:
                    fmt = grey
                    value = "V"
                elif expected_hours == 0:
                    fmt = grey
                    value = self._format_hours(worked_hours) if worked_hours else ""
                elif worked_hours == 0:
                    fmt = red
                    value = "00:00"
                elif worked_hours + 0.0001 < expected_hours:
                    fmt = yellow
                    value = self._format_hours(worked_hours)
                else:
                    fmt = green
                    value = self._format_hours(worked_hours)

                sheet.write(row, col, value, fmt)
                col += 1

            row += 1

        footer_row = row + 2
        footer_end_col = max(8, len(dates))
        sheet.merge_range(
            footer_row, 0, footer_row, footer_end_col,
            f"Creado por Overtime Bank Pro - Servi Byte Canarias SL - {datetime.now().year}",
            footer_format,
        )

        workbook.close()
        output.seek(0)

        attachment = self.env["ir.attachment"].create({
            "name": "reporte_asistencia.xlsx",
            "type": "binary",
            "datas": base64.b64encode(output.read()),
            "mimetype": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        })

        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "self",
        }

