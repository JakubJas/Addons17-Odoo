from odoo import api, fields, models, _
from odoo.exceptions import UserError


PROJECT_SEQUENCE_CODE = "sb.project.key"


class ProjectProject(models.Model):
    _inherit = "project.project"

    # project_key already defines this field. We only make it readonly in the UI.
    # The original size=10 is enough for the format 00001/2026.
    key = fields.Char(readonly=True)

    @api.onchange("name")
    def _onchange_project_name(self):
        """Do not generate initials while editing a new project.

        OCA project_key normally derives the key from the project name in this
        onchange. The definitive numeric key is assigned only when create() is
        executed, so opening/changing a form never consumes a sequence number.
        """
        for project in self:
            if not project._origin.id:
                project.key = False

    @api.model_create_multi
    def create(self, vals_list):
        """Assign an annual numeric key before project_key creates task sequence."""
        sequence_model = self.env["ir.sequence"]

        for vals in vals_list:
            key = sequence_model.next_by_code(PROJECT_SEQUENCE_CODE)
            if not key:
                raise UserError(
                    _(
                        "The project numbering sequence is not configured. "
                        "Please check sequence code '%s'."
                    )
                    % PROJECT_SEQUENCE_CODE
                )
            # Always enforce the official sequence, even if a key is supplied by
            # an import/API call.
            vals["key"] = key

        # OCA project_key sees that key is already populated and keeps its own
        # logic for creating the per-project task sequence.
        return super().create(vals_list)

    def write(self, values):
        """Prevent accidental/manual changes to an already assigned project key."""
        if "key" in values and not self.env.context.get("sb_allow_project_key_write"):
            requested_key = values.get("key")
            for project in self:
                if project.key and requested_key != project.key:
                    raise UserError(
                        _(
                            "The project key is an internal identifier and cannot "
                            "be changed after the project has been created."
                        )
                    )
        return super().write(values)

    def _prepare_sequence_data(self, init=True):
        """Keep OCA task keys, but format their counter with three digits.

        Example:
            Project: 00001/2026
            Tasks:   00001/2026-001, 00001/2026-002, ...
        """
        values = super()._prepare_sequence_data(init=init)
        values["padding"] = 3
        return values
