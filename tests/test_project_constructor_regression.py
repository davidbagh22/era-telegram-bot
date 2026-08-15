from __future__ import annotations

import unittest

from app.database.models import Project
from app.services.project_workflow_service import update_answers
from app.utils.constants import ProjectStatus


class ProjectConstructorRegressionTests(unittest.TestCase):
    def _project(self) -> Project:
        return Project(
            author_id=1,
            title="Исходное название",
            short_description="Исходная идея",
            status=ProjectStatus.DRAFT,
            form_data={"idea": "Исходная идея", "target_audience": "Студенты"},
        )

    def test_partial_step_does_not_overwrite_previous_answers(self) -> None:
        project = self._project()
        update_answers(project, {"title": "Новый проект"})
        self.assertEqual(project.form_data["title"], "Новый проект")
        self.assertEqual(project.form_data["idea"], "Исходная идея")
        self.assertEqual(project.form_data["target_audience"], "Студенты")

    def test_format_column_is_clipped_to_actual_database_limit(self) -> None:
        project = self._project()
        full_answer = "Ф" * 180
        update_answers(project, {"format": full_answer})
        self.assertEqual(project.form_data["format"], full_answer)
        self.assertEqual(project.format, "Ф" * 100)
        self.assertEqual(len(project.format), 100)

    def test_title_column_keeps_255_limit(self) -> None:
        project = self._project()
        update_answers(project, {"title": "Н" * 400})
        self.assertEqual(len(project.title), 255)
        self.assertEqual(len(project.form_data["title"]), 400)


if __name__ == "__main__":
    unittest.main()
