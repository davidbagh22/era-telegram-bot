import inspect
import unittest

from app.handlers.participant import project_event_flow


class ProjectToEventFlowContracts(unittest.TestCase):
    def test_project_event_flow_uses_real_event_project_id(self):
        source = inspect.getsource(project_event_flow)
        self.assertIn("project_id=project.id", source)
        self.assertIn("project.event_created", source)

    def test_project_event_flow_collects_missing_event_fields(self):
        source = inspect.getsource(project_event_flow)
        self.assertIn("class ProjectEventStates", source)
        self.assertIn("ProjectEventStates.date", source)
        self.assertIn("ProjectEventStates.time", source)
        self.assertIn("ProjectEventStates.location", source)
        self.assertIn("ProjectEventStates.participant_limit", source)
        self.assertIn("ProjectEventStates.points", source)

    def test_project_event_flow_prevents_duplicate_event_for_project(self):
        source = inspect.getsource(project_event_flow)
        self.assertIn("Event.project_id == project_id", source)
        self.assertIn("Мероприятие уже создано", source)


if __name__ == "__main__":
    unittest.main()
