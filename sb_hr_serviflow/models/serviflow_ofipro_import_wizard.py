
import base64
import csv
import io
import json
import re

from collections import Counter, defaultdict
from datetime import date, datetime
from html import escape

from odoo import fields, models, _
from odoo.exceptions import UserError


PAGE_SIZE = 40


class ServiflowOfiproImportWizard(models.TransientModel):
    _name = 'serviflow.ofipro.import.wizard'
    _description = 'Validacion de proyectos historicos OfiPro'

    file = fields.Binary(
        string='Archivo CSV',
        required=True,
        attachment=False,
    )

    filename = fields.Char(
        string='Nombre del archivo',
    )

    state = fields.Selection(
        [
            ('draft', 'Sin analizar'),
            ('validated', 'Analizado'),
        ],
        default='draft',
        readonly=True,
    )

    summary = fields.Html(
        string='Resumen de validacion',
        readonly=True,
        sanitize=True,
    )

    preview = fields.Text(
        string='Vista previa',
        readonly=True,
    )

    issues = fields.Text(
        string='Incidencias',
        readonly=True,
    )

    page = fields.Integer(
        string='Pagina actual',
        default=1,
        readonly=True,
    )

    total_pages = fields.Integer(
        string='Total de paginas',
        readonly=True,
    )

    total_rows = fields.Integer(
        string='Total de registros',
        readonly=True,
    )

    preview_data = fields.Text(
        string='Datos de validacion',
        readonly=True,
    )

    def _read_date(self, value):
        if isinstance(value, datetime):
            return value.date()

        if isinstance(value, date):
            return value

        value = str(value or '').strip()

        if not value:
            return None

        for fmt in (
            '%d/%m/%Y',
            '%d/%m/%Y %H:%M:%S',
            '%Y-%m-%d',
            '%Y-%m-%d %H:%M:%S',
            '%d-%m-%Y',
            '%d-%m-%Y %H:%M',
            '%Y-%m-%dT%H:%M:%S',
        ):
            try:
                return datetime.strptime(
                    value, fmt
                ).date()
            except ValueError:
                continue

        return None

    def _numeric_code(self, value):
        if value is None or isinstance(value, bool):
            return None

        raw = str(value).strip()

        if re.fullmatch(r'\d+\.0+', raw):
            raw = raw.split('.')[0]

        if not re.fullmatch(r'\d+', raw):
            return None

        return str(int(raw))

    def _read_csv(self):
        self.ensure_one()

        if not self.file:
            raise UserError(
                _('Debes seleccionar un archivo CSV.')
            )

        if not (
            self.filename or ''
        ).lower().endswith('.csv'):
            raise UserError(
                _('El archivo debe tener extension .csv.')
            )

        try:
            content = base64.b64decode(self.file)
        except Exception as exc:
            raise UserError(
                _('No se ha podido decodificar el archivo.')
            ) from exc

        if len(content) > 20 * 1024 * 1024:
            raise UserError(
                _('El CSV supera el limite de 20 MB.')
            )

        text = None

        for encoding in ('utf-8-sig', 'cp1252'):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            raise UserError(
                _('Codificacion CSV no reconocida.')
            )

        try:
            sample = text[:8192]

            try:
                dialect = csv.Sniffer().sniff(
                    sample,
                    delimiters=';,\t',
                )
                delimiter = dialect.delimiter

            except csv.Error:
                first_line = text.splitlines()[0]

                delimiter = (
                    ';'
                    if first_line.count(';') >=
                    first_line.count(',')
                    else ','
                )

            reader = csv.DictReader(
                io.StringIO(text, newline=''),
                delimiter=delimiter,
            )

            if not reader.fieldnames:
                raise UserError(
                    _('El CSV no tiene cabeceras.')
                )

            reader.fieldnames = [
                str(name or '').strip().upper()
                for name in reader.fieldnames
            ]

            required = [
                'A_CLIENTE__CODIGO',
                'A_CLIENTE__EMPRESA',
                'CODIGO',
                'FECHA_ENTREGA',
                'FECHA',
                'FIRME',
                'NOTAS',
                'ID_CLIENTE',
            ]

            missing = [
                name for name in required
                if name not in reader.fieldnames
            ]

            if missing:
                raise UserError(
                    _('Faltan columnas: %s')
                    % ', '.join(missing)
                )

            rows = []

            for line_number, values in enumerate(
                reader, start=2
            ):
                if not any(
                    str(value or '').strip()
                    for value in values.values()
                    if isinstance(value, str)
                ):
                    continue

                if None in values:
                    raise UserError(
                        _(
                            'Fila %s: hay mas columnas que '
                            'en la cabecera. Comprueba el '
                            'separador CSV.'
                        ) % line_number
                    )

                rows.append(
                    (line_number, values)
                )

            return rows

        except csv.Error as exc:
            raise UserError(
                _('Error leyendo CSV: %s')
                % str(exc)
            ) from exc

    def _build_preview_page(self, rows, page):
        start = (page - 1) * PAGE_SIZE
        end = start + PAGE_SIZE

        lines = [
            'Fila | Key | Cliente | Inicio | '
            'Entrega | Estado | Validacion'
        ]

        for row in rows[start:end]:
            errors = row.get('errors') or []

            validation = (
                'ERROR: ' + '; '.join(errors)
                if errors else 'OK'
            )

            lines.append(
                '%s | %s | %s | %s | %s | %s | %s'
                % (
                    row['line'],
                    row['key'],
                    row['partner_code'],
                    row['start'] or '-',
                    row['delivery'] or '-',
                    'Completo'
                    if row['completed']
                    else 'Pendiente',
                    validation,
                )
            )

        return '\n'.join(lines)

    def _show_page(self, new_page):
        self.ensure_one()

        if not self.preview_data:
            raise UserError(
                _('Primero debes analizar un archivo CSV.')
            )

        rows = json.loads(
            self.preview_data
        )

        new_page = max(
            1,
            min(new_page, self.total_pages),
        )

        self.write({
            'page': new_page,
            'preview': self._build_preview_page(
                rows, new_page
            ),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Validar proyectos OfiPro',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_next_page(self):
        self.ensure_one()
        return self._show_page(
            self.page + 1
        )

    def action_previous_page(self):
        self.ensure_one()
        return self._show_page(
            self.page - 1
        )

    def action_validate(self):
        self.ensure_one()

        source_rows = self._read_csv()

        if not source_rows:
            raise UserError(
                _('El CSV no contiene proyectos.')
            )

        rows = []
        seen_orders = set()

        for line_number, values in source_rows:

            code = self._numeric_code(
                values.get('A_CLIENTE__CODIGO')
            )

            check_code = self._numeric_code(
                values.get('ID_CLIENTE')
            )

            order = self._numeric_code(
                values.get('CODIGO')
            )

            start = self._read_date(
                values.get('FECHA')
            )

            delivery = self._read_date(
                values.get('FECHA_ENTREGA')
            )

            firm = str(
                values.get('FIRME') or ''
            ).strip().lower()

            errors = []

            if code is None or check_code != code:
                errors.append(
                    'Codigo de cliente invalido o distinto'
                )

            if order is None:
                errors.append(
                    'Codigo de pedido invalido'
                )

            elif order in seen_orders:
                errors.append(
                    'Codigo de pedido duplicado en CSV'
                )

            if order is not None:
                seen_orders.add(order)

            if start is None:
                errors.append(
                    'Fecha de inicio invalida'
                )

            if delivery is None:
                errors.append(
                    'Fecha de entrega invalida'
                )

            if firm in (
                '1', '1.0', 'true', 'si', 'sí'
            ):
                completed = True

            elif firm in (
                '0', '0.0', 'false', 'no'
            ):
                completed = False

            else:
                completed = False

                errors.append(
                    'Valor FIRME invalido: %s'
                    % firm
                )

            rows.append({
                'line': line_number,
                'code': code,
                'order': order,
                'start': start,
                'delivery': delivery,
                'completed': completed,
                'company': str(
                    values.get(
                        'A_CLIENTE__EMPRESA'
                    ) or ''
                ).strip(),
                'notes': str(
                    values.get('NOTAS') or ''
                ),
                'errors': errors,
            })

        # Vincular codigos OfiPro con Odoo.
        # Ejemplo: 579 -> C00579

        codes = {
            'C%s' % row['code'].zfill(5)
            for row in rows
            if row['code'] is not None
        }

        partners = (
            self.env['res.partner']
            .sudo()
            .search([
                (
                    'sequence_number',
                    'in',
                    list(codes),
                )
            ])
        )

        by_code = defaultdict(list)

        for partner in partners:
            by_code[
                partner.sequence_number
            ].append(partner)

        # Numeracion historica por fecha.

        years = Counter()

        sorted_rows = sorted(
            rows,
            key=lambda row: (
                row['start'] or date.max,
                int(row['order'])
                if row['order']
                else 10**15,
                row['line'],
            ),
        )

        for row in sorted_rows:

            if row['start']:
                year = row['start'].year
                years[year] += 1

                row['key'] = '%05d/%s' % (
                    years[year],
                    year,
                )

            else:
                row['key'] = 'SIN FECHA'

            row['partner_code'] = (
                'C%s' % row['code'].zfill(5)
                if row['code'] is not None
                else ''
            )

            matches = by_code.get(
                row['partner_code'], []
            )

            if not matches:
                row['errors'].append(
                    'Cliente no encontrado: %s'
                    % row['partner_code']
                )

            elif len(matches) > 1:
                row['errors'].append(
                    'Cliente duplicado en Odoo: %s'
                    % row['partner_code']
                )

            else:
                row['partner_name'] = (
                    matches[0].name
                )

        # Comprobar keys existentes en Odoo.

        planned_keys = [
            row['key']
            for row in rows
            if row['start']
        ]

        existing = (
            self.env['project.project']
            .sudo()
            .search([
                ('key', 'in', planned_keys)
            ])
        )

        used_keys = set(
            existing.mapped('key')
        )

        for row in rows:
            if row['key'] in used_keys:
                row['errors'].append(
                    'Key ya existente: %s'
                    % row['key']
                )

        invalid = sum(
            bool(row['errors'])
            for row in rows
        )

        completed = sum(
            row['completed']
            for row in rows
        )

        issues = []

        for row in rows:
            for error in row['errors']:
                issues.append(
                    'Fila %s | Pedido %s | %s'
                    % (
                        row['line'],
                        row['order'] or '-',
                        error,
                    )
                )

        # Guardar TODAS las filas de la validacion.

        preview_data = []

        for row in rows:
            preview_data.append({
                'line': row['line'],
                'key': row['key'],
                'partner_code': row['partner_code'],
                'start': str(
                    row['start'] or ''
                ),
                'delivery': str(
                    row['delivery'] or ''
                ),
                'completed': row['completed'],
                'errors': row['errors'],
            })

        total_pages = max(
            1,
            (
                len(preview_data)
                + PAGE_SIZE - 1
            ) // PAGE_SIZE,
        )

        preview_text = (
            self._build_preview_page(
                preview_data, 1
            )
        )

        year_text = ', '.join(
            '%s: %s' % (
                year,
                years[year],
            )
            for year in sorted(years)
        )

        self.write({
            'state': 'validated',
            'page': 1,
            'total_pages': total_pages,
            'total_rows': len(rows),
            'preview_data': json.dumps(
                preview_data,
                ensure_ascii=False,
            ),
            'summary': (
                '<p><b>Proyectos analizados:</b> %s</p>'
                '<p><b>Filas correctas:</b> %s</p>'
                '<p><b>Filas con incidencias:</b> %s</p>'
                '<p><b>Estado Completo:</b> %s</p>'
                '<p><b>Estado Pendiente:</b> %s</p>'
                '<p><b>Distribucion por año:</b> %s</p>'
                '<p><b>Importacion:</b> '
                'DESACTIVADA (solo validacion).</p>'
            ) % (
                len(rows),
                len(rows) - invalid,
                invalid,
                completed,
                len(rows) - completed,
                escape(year_text),
            ),
            'preview': preview_text,
            'issues': (
                '\n'.join(issues[:100])
                if issues
                else 'Sin incidencias detectadas.'
            ),
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Validar proyectos OfiPro',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }
