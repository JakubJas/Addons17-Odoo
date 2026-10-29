
from odoo import api, fields, models, _
from odoo.exceptions import UserError


PROJECT_SEQUENCE_CODE = "sb.project.key"


class ProjectProject(models.Model):
    _inherit = "project.project"

    # project_key define originalmente este campo.
    # Lo mantenemos como solo lectura en la interfaz.
    key = fields.Char(readonly=True)

    @api.onchange("name")
    def _onchange_project_name(self):
        """
        Evitar que project_key genere iniciales mientras
        se edita un proyecto nuevo.

        La numeracion definitiva se asigna en create().
        """
        for project in self:
            if not project._origin.id:
                project.key = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Numeracion automatica anual de proyectos.

        Funcionamiento normal:
            00001/2026
            00002/2026
            00003/2026

        Importacion historica OfiPro:
            00001/2018
            00002/2018
            00003/2018

        La importacion historica no consume numeros
        de la secuencia anual actual.
        """

        sequence_model = self.env["ir.sequence"]

        historical_import = self.env.context.get(
            "serviflow_ofipro_import"
        )

        for vals in vals_list:

            # =============================================
            # IMPORTACION HISTORICA OFIPRO
            # =============================================

            if historical_import:

                historical_key = vals.get("key")

                if not historical_key:
                    raise UserError(
                        _(
                            "La importacion historica OfiPro "
                            "requiere una clave de proyecto."
                        )
                    )

                # Comprobar que la clave no existe.
                existing_project = self.search(
                    [
                        ("key", "=", historical_key)
                    ],
                    limit=1,
                )

                if existing_project:
                    raise UserError(
                        _(
                            "Ya existe un proyecto con "
                            "la clave historica %s."
                        )
                        % historical_key
                    )

                # Conservar la clave proporcionada.
                # No consumir la secuencia anual.
                vals["key"] = historical_key

                continue

            # =============================================
            # CREACION NORMAL DE PROYECTOS
            # =============================================

            key = sequence_model.next_by_code(
                PROJECT_SEQUENCE_CODE
            )

            if not key:
                raise UserError(
                    _(
                        "La secuencia de numeracion de "
                        "proyectos no esta configurada. "
                        "Comprueba el codigo '%s'."
                    )
                    % PROJECT_SEQUENCE_CODE
                )

            # Mantener el comportamiento original:
            # ignorar claves externas y generar la oficial.
            vals["key"] = key

        # OCA project_key conserva la clave asignada
        # y crea su secuencia interna para las tareas.
        return super().create(vals_list)

    def write(self, values):
        """
        Impedir modificaciones de la clave una vez
        creado el proyecto.

        Esta proteccion tambien se aplica a los
        proyectos importados desde OfiPro.
        """

        if (
            "key" in values
            and not self.env.context.get(
                "sb_allow_project_key_write"
            )
        ):

            requested_key = values.get("key")

            for project in self:

                if (
                    project.key
                    and requested_key != project.key
                ):
                    raise UserError(
                        _(
                            "The project key is an internal "
                            "identifier and cannot be changed "
                            "after the project has been created."
                        )
                    )

        return super().write(values)

    def _prepare_sequence_data(self, init=True):
        """
        Mantener la numeracion de tareas de OCA
        con tres digitos.

        Ejemplo:

            Proyecto: 00001/2026

            Tareas:
                00001/2026-001
                00001/2026-002
                00001/2026-003
        """

        values = super()._prepare_sequence_data(
            init=init
        )

        values["padding"] = 3

        return values
