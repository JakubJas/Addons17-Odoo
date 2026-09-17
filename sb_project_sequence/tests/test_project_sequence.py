from odoo.tests.common import TransactionCase


class TestProjectSequence(TransactionCase):
    def test_project_and_task_key_format(self):
        project = self.env["project.project"].create({"name": "Sequence Test"})

        self.assertRegex(project.key, r"^\d{5}/\d{4}$")

        task = self.env["project.task"].create(
            {
                "name": "First Task",
                "project_id": project.id,
            }
        )
        self.assertEqual(task.key, f"{project.key}-001")

    def test_project_key_is_not_reused_from_input(self):
        project = self.env["project.project"].create(
            {
                "name": "Forced Input Test",
                "key": "MANUAL",
            }
        )
        self.assertNotEqual(project.key, "MANUAL")
        self.assertRegex(project.key, r"^\d{5}/\d{4}$")
