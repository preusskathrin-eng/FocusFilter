import os
from pathlib import Path
import shutil
import tempfile
import unittest

IN_CODEX_SANDBOX = os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1"
if not IN_CODEX_SANDBOX:
    from streamlit.testing.v1 import AppTest


@unittest.skipIf(
    IN_CODEX_SANDBOX,
    "Streamlit AppTest benötigt ein lokales Socketpaar, das die Codex-Sandbox blockiert.",
)
class NavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_directory = Path(__file__).resolve().parent
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="navigation_", dir=test_directory
        )
        temporary_root = Path(cls._temporary_directory.name)
        database_source = (
            Path(__file__).resolve().parents[1] / "examples" / "tasks.example.db"
        )
        cls.database_path = temporary_root / "tasks.db"
        shutil.copy2(database_source, cls.database_path)
        os.environ["TASK_PLANNER_DB_PATH"] = str(cls.database_path)
        os.environ["TASK_PLANNER_BACKUP_DIR"] = str(temporary_root / "backups")

    @classmethod
    def tearDownClass(cls):
        os.environ.pop("TASK_PLANNER_DB_PATH", None)
        os.environ.pop("TASK_PLANNER_BACKUP_DIR", None)
        cls._temporary_directory.cleanup()

    def test_every_registered_page_opens_without_exception(self):
        root = Path(__file__).resolve().parents[1]
        entrypoint = root / "streamlit_app.py"
        pages = [
            "app_pages/today.py",
            "app_pages/overview.py",
            "app_pages/new_task.py",
            "app_pages/weekly_review.py",
            "app_pages/statistics.py",
            "app_pages/timeline.py",
            "app_pages/csv_import.py",
            "app_pages/projects.py",
        ]

        app = AppTest.from_file(entrypoint, default_timeout=20).run()
        self.assertFalse(app.exception)

        for page in pages[1:]:
            with self.subTest(page=page):
                app.switch_page(page).run(timeout=20)
                self.assertFalse(app.exception)

    def test_statistics_can_include_completed_tasks(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        app.switch_page("app_pages/statistics.py").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                "erledigte Tasks sind ausgeblendet" in caption.value
                for caption in app.caption
            )
        )

        app.get_by_key("statistics_include_done").set_value(True).run(timeout=20)
        self.assertFalse(app.exception)
        self.assertTrue(
            any(
                "einschließlich erledigter Tasks" in caption.value
                for caption in app.caption
            )
        )

    def test_timeline_period_can_switch_from_today_to_all(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        app.switch_page("app_pages/timeline.py").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.get_by_key("timeline_period_mode").value, "Ab heute")

        app.get_by_key("timeline_period_mode").set_value("Alles").run(timeout=20)
        self.assertFalse(app.exception)
        self.assertEqual(app.get_by_key("timeline_period_mode").value, "Alles")

    def test_overview_search_accepts_a_term(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        app.switch_page("app_pages/overview.py").run(timeout=20)
        self.assertFalse(app.exception)

        app.get_by_key("task_search").set_value("Beispiel").run(timeout=20)

        self.assertFalse(app.exception)
        self.assertEqual(app.get_by_key("task_search").value, "Beispiel")

    def test_today_uses_category_as_third_focus_filter(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        app.switch_page("app_pages/today.py").run(timeout=20)

        self.assertFalse(app.exception)
        category_filter = app.get_by_key("today_categories")
        self.assertEqual(category_filter.label, "Kategorie")

    def test_new_task_exposes_recurrence_controls(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        app.switch_page("app_pages/new_task.py").run(timeout=20)

        self.assertFalse(app.exception)
        recurrence = app.get_by_key("new_task_recurrence_preset")
        self.assertEqual(recurrence.label, "Wiederholung")
        self.assertEqual(recurrence.value, "Nicht wiederkehrend")

    def test_recurrence_controls_accept_empty_values_from_dataframe(self):
        app = AppTest.from_string(
            """
from app_shared import recurrence_form_controls

recurrence_form_controls(
    "empty_recurrence",
    {
        "recurrence_interval": float("nan"),
        "recurrence_unit": float("nan"),
        "recurrence_anchor": float("nan"),
    },
)
"""
        ).run(timeout=20)

        self.assertFalse(app.exception)
        self.assertEqual(
            app.get_by_key("empty_recurrence_recurrence_interval").value,
            1,
        )


if __name__ == "__main__":
    unittest.main()
