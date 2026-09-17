# Servibyte Project Sequence

Extension for Odoo 17 + OCA `project_key`.

## Project numbering

New projects receive an automatic annual key:

- `00001/2026`
- `00002/2026`
- `00003/2026`

The counter resets automatically for each year by using an `ir.sequence` with date ranges.

## Task numbering

OCA `project_key` continues managing the per-project task sequence. This module only changes its padding to three digits:

- `00001/2026-001`
- `00001/2026-002`

## Important implementation detail

OCA `project_key` marks the project key as required in its project form view. Since this module assigns the official numeric key inside `create()`, the inherited Servibyte view changes the field to `required="0"` and `readonly="1"`. This allows a new unsaved project to have an empty Key until it is saved.

## Updating

After replacing the module files, restart Odoo and upgrade `sb_project_sequence` (`-u sb_project_sequence`) so the inherited view is loaded.
