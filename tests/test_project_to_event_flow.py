import inspect
import unittest
from datetime import date, time

from app.database.models import Project
from app.handlers.participant import project_event_photo_flow


class ProjectToEventFlowContracts(unittest.TestCase):
    def test_project_event_flow_uses_real_event_project_id(self):
        source = inspect.getsource(project_event_photo_flow)
        self.assertIn("project_id=project.id", source)
        self.assertIn("event.submitted_from_project", source)
        self.assertIn("poster_file_id", source)

    def test_project_event_flow_collects_missing_event_fields(self):
        source = inspect.getsource(project_event_photo_flow)
        self.assertIn("class ProjectEventStates", source)
        self.assertIn("ProjectEventStates.event_date", source)
        self.assertIn("ProjectEventStates.event_time", source)
        self.assertIn("ProjectEventStates.location", source)
        self.assertIn("ProjectEventStates.participant_limit", source)
        self.assertIn("ProjectEventStates.points", source)
        self.assertIn("ProjectEventStates.poster", source)

    def test_project_event_flow_prevents_duplicate_event_for_project(self):
        source = inspect.getsource(project_event_photo_flow)
        self.assertIn("Event.project_id == project_id", source)
        self.assertIn("Мероприятие уже создано", source)

    def test_project_event_flow_uses_structured_date_and_time_first(self):
        project = Project(
            author_id=1,
            title="Project",
            short_description="Description",
            form_data={"proposed_date": "01.01.2020", "proposed_time": "09:00"},
        )
        project.proposed_date = date(2026, 9, 15)
        project.proposed_time = time(18, 30)

        data = project.form_data

        self.assertEqual(
            project_event_photo_flow._date_string(project.proposed_date or data.get("proposed_date")),
            "15.09.2026",
        )
        self.assertEqual(
            project_event_photo_flow._time_string(project.proposed_time or data.get("proposed_time")),
            "18:30",
        )


if __name__ == "__main__":
    unittest.main()
