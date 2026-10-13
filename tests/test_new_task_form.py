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
class NewTaskFormTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        example_database = root / "examples" / "tasks.example.db"
        database_source = example_database if example_database.exists() else root / "tasks.db"
        cls._temporary_directory = tempfile.TemporaryDirectory(
            prefix="new_task_form_", dir=Path(__file__).resolve().parent
        )
        temporary_root = Path(cls._temporary_directory.name)
        cls.database_path = temporary_root / "tasks.db"
        shutil.copy2(database_source, cls.database_path)
        os.environ["TASK_PLANNER_DB_PATH"] = str(cls.database_path)
        os.environ["TASK_PLANNER_BACKUP_DIR"] = str(temporary_root / "backups")
        import app_shared

        cls._original_db_path = app_shared.DB_PATH
        cls._original_backup_dir = app_shared.BACKUP_DIR
        app_shared.DB_PATH = cls.database_path
        app_shared.BACKUP_DIR = temporary_root / "backups"

    @classmethod
    def tearDownClass(cls):
        import app_shared

        app_shared.DB_PATH = cls._original_db_path
        app_shared.BACKUP_DIR = cls._original_backup_dir
        os.environ.pop("TASK_PLANNER_DB_PATH", None)
        os.environ.pop("TASK_PLANNER_BACKUP_DIR", None)
        cls._temporary_directory.cleanup()

    def open_new_task_page(self):
        root = Path(__file__).resolve().parents[1]
        app = AppTest.from_file(root / "streamlit_app.py", default_timeout=20).run()
        return app.switch_page("app_pages/new_task.py").run(timeout=20)

    def test_required_fields_are_marked_and_invalid_submit_keeps_values(self):
        app = self.open_new_task_page()
        self.assertFalse(app.exception)
        self.assertEqual(app.get_by_key("new_task_title").label, "Titel *")
        self.assertEqual(
            app.get_by_key("new_task_project").label, "Projekt/Subprojekt *"
        )
        self.assertEqual(
            app.get_by_key("new_task_category").label, "Hauptkategorie *"
        )

        app.get_by_key("new_task_micro_action").set_value(
            "Dieser Text darf nicht verschwinden"
        )
        app.get_by_key("new_task_submit").click().run(timeout=20)

        self.assertFalse(app.exception)
        self.assertTrue(
            any("Pflichtfeld „Titel“" in error.value for error in app.error)
        )
        self.assertEqual(
            app.get_by_key("new_task_micro_action").value,
            "Dieser Text darf nicht verschwinden",
        )


if __name__ == "__main__":
    unittest.main()
