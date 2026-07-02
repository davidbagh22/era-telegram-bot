from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HANDLER_FILES = (
    "app/handlers/admin/dashboard_block_a.py",
    "app/handlers/admin/task_review_block2.py",
    "app/handlers/admin/projects_block5_list.py",
    "app/handlers/admin/projects_block5_decision.py",
    "app/handlers/admin/events_block6.py",
    "app/handlers/admin/panel.py",
    "app/handlers/participant/task_block2.py",
    "app/handlers/participant/projects_block5.py",
    "app/handlers/participant/event_plans_changed.py",
    "app/handlers/participant/cabinet.py",
    "app/handlers/participant/growth.py",
    "app/handlers/participant/projects.py",
    "app/handlers/leader/events_block6.py",
    "app/handlers/leader/panel.py",
)


def sources() -> str:
    return "\n".join((ROOT / path).read_text(encoding="utf-8") for path in HANDLER_FILES)


class RouterOwnershipTests(unittest.TestCase):
    def test_exact_callbacks_have_one_owner(self):
        source = sources()
        expressions = (
            'F.data == "admin:panel"',
            'F.data == "admin:events"',
            'F.data == "admin:tasks"',
            'F.data == "cabinet:tasks"',
            'F.data == "cabinet:events"',
            'F.data.in_({"cabinet:projects", "projects:drafts"})',
            'F.data == "leader:event:new"',
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertEqual(source.count(expression), 1)

    def test_prefixed_callbacks_have_one_owner(self):
        source = sources()
        expressions = (
            'F.data.startswith("task:join:")',
            'F.data.startswith("task:view:")',
            'F.data.startswith("task:result:")',
            'F.data.startswith("project:submit:")',
            'F.data.startswith("admin:event:approve:")',
            'F.data.startswith("admin:project:review:")',
        )
        for expression in expressions:
            with self.subTest(expression=expression):
                self.assertEqual(source.count(expression), 1)

    def test_dashboard_is_compact_and_queue_driven(self):
        source = (ROOT / "app/handlers/admin/dashboard_block_a.py").read_text(encoding="utf-8")
        self.assertIn("Центр управления ЭРА", source)
        self.assertIn("Очередь чиста", source)
        self.assertIn("active = [(label, callback, amount)", source)


if __name__ == "__main__":
    unittest.main()
