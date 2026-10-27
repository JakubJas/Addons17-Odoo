
import base64
import csv
import io
import json
import re

from collections import Counter, defaultdict
from datetime import datetime

from odoo import fields, models, _
from odoo.exceptions import UserError


PAGE_SIZE = 40
BATCH_SIZE = 100


class ServiflowOfiproImportWizard(models.TransientModel):
    _name = 'serviflow.ofipro.import.wizard'
    _description = 'Importacion historica de proyectos OfiPro'

    batch_id = fields.Many2one(
        'serviflow.ofipro.batch',
        string='Lote de importacion',
        readonly=True,
    )

    file = fields.Binary(
        string='Archivo CSV',
        required=True,
        attachment=False,
    )

    filename = fields.Char(string='Nombre del archivo')

    state = fields.Selection([
        ('draft', 'Sin analizar'),
        ('validated', 'Validado'),
        ('importing', 'Importacion en curso'),
        ('done', 'Finalizado'),
    ], default='draft', readonly=True)

    summary = fields.Html(
        string='Resumen',
        readonly=True,
        sanitize=True,
    )

    preview = fields.Text(
        string='Vista previa',
        readonly=True,
    )

    issues = fields.Text(
        string='Detalle de incidencias y omisiones',
        readonly=True,
    )

    page = fields.Integer(default=1, readonly=True)
    total_pages = fields.Integer(readonly=True)
    total_rows = fields.Integer(readonly=True)
    preview_data = fields.Text(readonly=True)
    cursor = fields.Integer(default=0, readonly=True)

    imported_count = fields.Integer(readonly=True)
    missing_count = fields.Integer(readonly=True)
    duplicate_count = fields.Integer(readonly=True)
    invalid_count = fields.Integer(readonly=True)
    existing_count = fields.Integer(readonly=True)
    failed_count = fields.Integer(readonly=True)

    import_log = fields.Text(readonly=True)

    # =====================================================
    # UTILIDADES
    # =====================================================

    def _read_date(self, value):
        value = str(value or '').strip()

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
                return datetime.strptime(value, fmt).date()
            except ValueError:
                pass

        return None

    def _numeric_code(self, value):
        raw = str(value or '').strip()

        if re.fullmatch(r'\d+\.0+', raw):
            raw = raw.split('.')[0]

        if re.fullmatch(r'\d+', raw):
            return str(int(raw))

        return None

    def _read_csv(self):
        self.ensure_one()

        if not self.file or not (
            self.filename or ''
        ).lower().endswith('.csv'):
            raise UserError(
                _('Selecciona un archivo .csv.')
            )

        content = base64.b64decode(self.file)

        if len(content) > 20 * 1024 * 1024:
            raise UserError(
                _('El CSV supera los 20 MB.')
            )

        try:
            text = content.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = content.decode('cp1252')

        sample = text[:8192]

        try:
            delimiter = csv.Sniffer().sniff(
                sample,
                delimiters=';,\t',
            ).delimiter
        except csv.Error:
            first = (
                text.splitlines()[0]
                if text.splitlines()
                else ''
            )
            delimiter = (
                ';'
                if first.count(';') >= first.count(',')
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
            str(x or '').strip().upper()
            for x in reader.fieldnames
        ]

        required = (
            'A_CLIENTE__CODIGO',
            'A_CLIENTE__EMPRESA',
            'CODIGO',
            'FECHA_ENTREGA',
            'FECHA',
            'FIRME',
            'NOTAS',
            'ID_CLIENTE',
        )

        missing = [
            x for x in required
            if x not in reader.fieldnames
        ]

        if missing:
            raise UserError(
                _('Faltan columnas: %s')
                % ', '.join(missing)
            )

        result = []

        try:
            for line, values in enumerate(reader, 2):
                if None in values:
                    raise UserError(
                        _('Fila %s: separador CSV incorrecto.')
                        % line
                    )

                if not any(
                    str(v or '').strip()
                    for v in values.values()
                ):
                    continue

                result.append((line, values))

        except csv.Error as exc:
            raise UserError(
                _('Error leyendo CSV: %s')
                % exc
            ) from exc

        return result

    # =====================================================
    # NAVEGACION
    # =====================================================

    def _open_wizard(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Importar proyectos historicos OfiPro',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _build_preview_page(self, rows, page):
        lines = [
            'Fila | Key | Pedido | Cliente | Inicio | '
            'Entrega | Estado | Resultado'
        ]

        start = (page - 1) * PAGE_SIZE
        end = page * PAGE_SIZE

        for row in rows[start:end]:
            errors = row.get('errors') or []

            result = row.get('result') or (
                'ERROR: ' + '; '.join(errors)
                if errors
                else 'OK'
            )

            lines.append(
                '%s | %s | %s | %s | %s | %s | %s | %s'
                % (
                    row['line'],
                    row['key'],
                    row['order'] or '-',
                    row['partner_code'],
                    row['start'] or '-',
                    row['delivery'] or '-',
                    'Completo'
                    if row['completed']
                    else 'Pendiente',
                    result,
                )
            )

        return '\n'.join(lines)

    def _show_page(self, number):
        self.ensure_one()

        if not self.preview_data:
            raise UserError(
                _('Analiza primero el CSV.')
            )

        rows = json.loads(self.preview_data)

        page = max(
            1,
            min(number, self.total_pages),
        )

        self.write({
            'page': page,
            'preview': self._build_preview_page(
                rows, page
            ),
        })

        return self._open_wizard()

    def action_next_page(self):
        self.ensure_one()
        return self._show_page(self.page + 1)

    def action_previous_page(self):
        self.ensure_one()
        return self._show_page(self.page - 1)

    # =====================================================
    # RESUMEN
    # =====================================================

    def _summary_html(
        self, rows, counters=None, cursor=0
    ):
        counters = counters or {}

        invalid = sum(
            bool(row['errors'])
            for row in rows
        )

        parts = [
            '<p><b>Proyectos analizados:</b> %s</p>'
            % len(rows),
            '<p><b>Validos inicialmente:</b> %s</p>'
            % (len(rows) - invalid),
            '<p><b>Con incidencias iniciales:</b> %s</p>'
            % invalid,
            '<p><b>Completos en CSV:</b> %s</p>'
            % sum(row['completed'] for row in rows),
            '<p><b>Pendientes en CSV:</b> %s</p>'
            % sum(not row['completed'] for row in rows),
            '<p><b>Procesados:</b> %s / %s</p>'
            % (cursor, len(rows)),
        ]

        if cursor:
            labels = (
                ('Importados', 'imported_count'),
                ('Sin cliente', 'missing_count'),
                ('Cliente duplicado', 'duplicate_count'),
                ('Datos invalidos', 'invalid_count'),
                ('Key existente', 'existing_count'),
                ('Errores de creacion', 'failed_count'),
            )

            for label, key in labels:
                parts.append(
                    '<p><b>%s:</b> %s</p>'
                    % (label, counters.get(key, 0))
                )

            skipped = sum(
                counters.get(key, 0)
                for key in (
                    'missing_count',
                    'duplicate_count',
                    'invalid_count',
                    'existing_count',
                    'failed_count',
                )
            )

            parts.append(
                '<p><b>Total no importados:</b> %s</p>'
                % skipped
            )

        if cursor == len(rows) and cursor:
            status = 'FINALIZADO'
        elif cursor:
            status = 'EN CURSO'
        else:
            status = 'PENDIENTE DE IMPORTAR'

        parts.append(
            '<p><b>Estado:</b> %s</p>'
            % status
        )

        return ''.join(parts)

    # =====================================================
    # VALIDAR
    # =====================================================

    def action_validate(self):
        self.ensure_one()

        if self.state != 'draft':
            raise UserError(
                _('Este asistente ya fue validado.')
            )

        source = self._read_csv()

        if not source:
            raise UserError(
                _('El CSV esta vacio.')
            )

        rows = []
        seen_orders = set()

        for line, values in source:
            code = self._numeric_code(
                values.get('A_CLIENTE__CODIGO')
            )

            check = self._numeric_code(
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

            if code is None or check != code:
                errors.append(
                    'Codigo de cliente invalido o distinto'
                )

            if order is None:
                errors.append(
                    'Codigo de pedido invalido'
                )
            elif order in seen_orders:
                errors.append(
                    'Pedido duplicado en CSV'
                )

            if order is not None:
                seen_orders.add(order)

            if not start:
                errors.append(
                    'Fecha de inicio invalida'
                )

            if not delivery:
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
                    'FIRME invalido: %s' % firm
                )

            rows.append({
                'line': line,
                'code': code,
                'order': order,
                'start': (
                    start.isoformat()
                    if start else ''
                ),
                'delivery': (
                    delivery.isoformat()
                    if delivery else ''
                ),
                'completed': completed,
                'company': str(
                    values.get('A_CLIENTE__EMPRESA') or ''
                ).strip(),
                'notes': str(
                    values.get('NOTAS') or ''
                ),
                'errors': errors,
            })

        # Buscar clientes

        codes = {
            'C%s' % row['code'].zfill(5)
            for row in rows
            if row['code'] is not None
        }

        partners = self.env[
            'res.partner'
        ].sudo().search([
            ('sequence_number', 'in', list(codes))
        ])

        by_code = defaultdict(list)

        for partner in partners:
            by_code[
                partner.sequence_number
            ].append(partner.id)

        # Calcular keys historicas

        sorted_rows = sorted(
            rows,
            key=lambda row: (
                row['start'] or '9999-12-31',
                int(row['order'])
                if row['order']
                else 10**15,
                row['line'],
            ),
        )

        years = Counter()

        for row in sorted_rows:
            if row['start']:
                year = row['start'][:4]
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

            row['partner_id'] = (
                matches[0]
                if len(matches) == 1
                else False
            )

            if not matches:
                row['errors'].append(
                    'Cliente no encontrado: %s'
                    % row['partner_code']
                )
            elif len(matches) > 1:
                row['errors'].append(
                    'Cliente duplicado: %s (%s contactos)'
                    % (
                        row['partner_code'],
                        len(matches),
                    )
                )

        project_model = self.env[
            'project.project'
        ].sudo()

        if 'key' not in project_model._fields:
            raise UserError(
                _('No existe el campo key en proyectos.')
            )

        keys = [
            row['key']
            for row in rows
            if row['start']
        ]

        existing = set(
            project_model.search([
                ('key', 'in', keys)
            ]).mapped('key')
        )

        for row in rows:
            if row['key'] in existing:
                row['errors'].append(
                    'Key ya existente: %s'
                    % row['key']
                )

        issues = [
            'Fila %s | Pedido %s | %s'
            % (
                row['line'],
                row['order'] or '-',
                error,
            )
            for row in rows
            for error in row['errors']
        ]

        self.write({
            'state': 'validated',
            'page': 1,
            'total_pages': max(
                1,
                (len(rows) + PAGE_SIZE - 1)
                // PAGE_SIZE,
            ),
            'total_rows': len(rows),
            'preview_data': json.dumps(
                rows,
                ensure_ascii=False,
            ),
            'preview': self._build_preview_page(
                rows, 1
            ),
            'issues': (
                '\n'.join(issues)
                if issues
                else 'Sin incidencias.'
            ),
            'summary': self._summary_html(rows),
            'import_log': '',
            'cursor': 0,
            'imported_count': 0,
            'missing_count': 0,
            'duplicate_count': 0,
            'invalid_count': 0,
            'existing_count': 0,
            'failed_count': 0,
        })

        return self._open_wizard()

    # =====================================================
    # IMPORTAR 100 REGISTROS
    # =====================================================

    def action_import_batch(self):
        self.ensure_one()

        if self.state not in (
            'validated', 'importing'
        ) or not self.preview_data:
            raise UserError(
                _('Primero debes validar el CSV.')
            )

        self.env.cr.execute(
            'SELECT pg_advisory_xact_lock(%s)',
            (81736251,),
        )

        self.invalidate_recordset()

        if self.state not in ('validated', 'importing'):
            raise UserError(
                _('Esta importacion ya ha finalizado.')
            )

        rows = json.loads(self.preview_data)

        if self.cursor >= len(rows):
            raise UserError(
                _('La importacion ya esta finalizada.')
            )

        project_model = self.env[
            'project.project'
        ].sudo()

        required_fields = (
            'key',
            'partner_id',
            'ofipro_batch_id',
        )

        missing_fields = [
            name for name in required_fields
            if name not in project_model._fields
        ]

        if missing_fields:
            raise UserError(
                _('Faltan campos en proyectos: %s')
                % ', '.join(missing_fields)
            )

        # Crear lote permanente en la primera ejecucion

        batch_record = self.batch_id

        if not batch_record:
            batch_record = self.env[
                'serviflow.ofipro.batch'
            ].create({
                'name': (
                    'OfiPro - %s'
                    % fields.Datetime.now().strftime(
                        '%Y-%m-%d %H:%M:%S'
                    )
                ),
                'filename': self.filename,
            })

            self.write({
                'batch_id': batch_record.id
            })

        if batch_record.state != 'active':
            raise UserError(
                _(
                    'Este lote ya fue revertido o tiene '
                    'una reversion parcial. No puede '
                    'continuar importandose.'
                )
            )

        counter_names = (
            'imported_count',
            'missing_count',
            'duplicate_count',
            'invalid_count',
            'existing_count',
            'failed_count',
        )

        counters = {
            name: getattr(self, name)
            for name in counter_names
        }

        log_lines = (
            (self.import_log or '').splitlines()
        )

        end = min(
            self.cursor + BATCH_SIZE,
            len(rows),
        )

        batch = rows[self.cursor:end]

        keys = [
            row['key']
            for row in batch
            if row['key'] != 'SIN FECHA'
        ]

        used_keys = set(
            project_model.search([
                ('key', 'in', keys)
            ]).mapped('key')
        )

        partner_ids = [
            row['partner_id']
            for row in batch
            if row.get('partner_id')
        ]

        available_partners = set(
            self.env['res.partner']
            .sudo()
            .browse(partner_ids)
            .exists()
            .ids
        )

        status_ids = {}

        if (
            'project_status' in project_model._fields
            and 'project.status'
            in self.env.registry.models
        ):
            status_model = self.env[
                'project.status'
            ].sudo()

            for name in ('Completo', 'Pendiente'):
                status = status_model.search([
                    ('name', '=', name)
                ], limit=1)

                if status:
                    status_ids[name] = status.id

        for row in batch:
            label = (
                'Fila %s | Pedido %s | %s | %s'
                % (
                    row['line'],
                    row['order'] or '-',
                    row['key'],
                    row['partner_code'],
                )
            )

            errors = row.get('errors') or []

            if any(
                'Cliente duplicado:' in error
                for error in errors
            ):
                reason = 'OMITIDO: cliente duplicado'
                counter = 'duplicate_count'

            elif (
                any(
                    'Cliente no encontrado:' in error
                    for error in errors
                )
                or row.get('partner_id')
                not in available_partners
            ):
                reason = 'OMITIDO: cliente inexistente'
                counter = 'missing_count'

            elif errors and any(
                'Key ya existente:' not in error
                for error in errors
            ):
                reason = (
                    'OMITIDO: '
                    + '; '.join(errors)
                )
                counter = 'invalid_count'

            elif row['key'] in used_keys:
                reason = 'OMITIDO: key ya existente'
                counter = 'existing_count'

            else:
                name = (
                    'OfiPro %s - %s'
                    % (
                        row['order'],
                        row['company']
                        or row['partner_code'],
                    )
                )[:250]

                description = (
                    'Importado desde OfiPro (historico).\n'
                    'Pedido OfiPro: %s\n'
                    'Cliente: %s\n'
                    'Fecha: %s\n'
                    'Entrega: %s\n'
                    'Estado original: %s\n\n%s'
                ) % (
                    row['order'],
                    row['partner_code'],
                    row['start'],
                    row['delivery'],
                    'Completo'
                    if row['completed']
                    else 'Pendiente',
                    row['notes'],
                )

                vals = {
                    'name': name,
                    'key': row['key'],
                    'partner_id': row['partner_id'],
                    'ofipro_batch_id': batch_record.id,
                }

                if 'description' in project_model._fields:
                    vals['description'] = description

                if 'date_start' in project_model._fields:
                    vals['date_start'] = row['start']

                if (
                    'date' in project_model._fields
                    and project_model._fields['date'].type
                    == 'date'
                ):
                    vals['date'] = row['delivery']
                elif 'date_deadline' in project_model._fields:
                    vals['date_deadline'] = row['delivery']

                status_name = (
                    'Completo'
                    if row['completed']
                    else 'Pendiente'
                )

                if status_name in status_ids:
                    vals['project_status'] = (
                        status_ids[status_name]
                    )

                try:
                    with self.env.cr.savepoint():
                        project = project_model.create(vals)

                        if project.key != row['key']:
                            raise UserError(
                                'La numeracion automatica '
                                'ha cambiado la key %s por %s'
                                % (
                                    row['key'],
                                    project.key,
                                )
                            )

                    used_keys.add(row['key'])

                    reason = (
                        'IMPORTADO: proyecto ID %s'
                        % project.id
                    )
                    counter = 'imported_count'

                except Exception as exc:
                    reason = (
                        'ERROR DE CREACION: %s'
                        % str(exc)[:350]
                    )
                    counter = 'failed_count'

            counters[counter] += 1
            row['result'] = reason

            if counter != 'imported_count':
                log_lines.append(
                    label + ' | ' + reason
                )

        batch_record.write({
            'imported_total': counters['imported_count'],
        })

        new_state = (
            'done'
            if end >= len(rows)
            else 'importing'
        )

        self.write({
            **counters,
            'state': new_state,
            'cursor': end,
            'preview_data': json.dumps(
                rows,
                ensure_ascii=False,
            ),
            'preview': self._build_preview_page(
                rows, self.page
            ),
            'summary': self._summary_html(
                rows, counters, end
            ),
            'import_log': '\n'.join(log_lines),
            'issues': (
                '\n'.join(log_lines)
                if log_lines
                else 'Sin omisiones ni errores.'
            ),
        })

        return self._open_wizard()
