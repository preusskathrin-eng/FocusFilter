from datetime import date
import sqlite3
import unittest

import pandas as pd

from utils.task_logic import (
    align_timeline_starts_with_dependencies,
    available_now_mask,
    classify_import_data,
    dependency_is_done,
    normalize_import_data,
    parse_duration_minutes,
    read_csv_bytes,
    task_hint,
    task_text_search_mask,
    timeline_overlap_mask,
    timeline_task_mask,
)
from utils.task_importer import apply_task_import
from utils.recurrence import (
    add_recurrence_interval,
    complete_task,
    next_occurrence_dates,
    recurrence_interval_value,
    recurrence_label,
    recurrence_preset,
    recurrence_text_value,
)


class TaskLogicTests(unittest.TestCase):
    def test_empty_dataframe_recurrence_values_are_treated_as_not_recurring(self):
        self.assertEqual(recurrence_interval_value(float("nan"), 1), 1)
        self.assertIsNone(recurrence_text_value(float("nan")))
        self.assertEqual(
            recurrence_preset(float("nan"), float("nan")),
            "Nicht wiederkehrend",
        )
        self.assertEqual(
            recurrence_label(
                {
                    "recurrence_interval": float("nan"),
                    "recurrence_unit": float("nan"),
                    "recurrence_anchor": float("nan"),
                }
            ),
            "",
        )

    def test_monthly_recurrence_keeps_the_preferred_calendar_day(self):
        february = add_recurrence_interval(
            date(2027, 1, 31), 1, "months", preferred_day=31
        )
        march = add_recurrence_interval(
            february, 1, "months", preferred_day=31
        )
        self.assertEqual(february, date(2027, 2, 28))
        self.assertEqual(march, date(2027, 3, 31))

    def test_completing_recurring_task_creates_exactly_one_successor(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, project TEXT,
                category TEXT NOT NULL, core_focus TEXT, priority INTEGER,
                start_date TEXT, deadline TEXT, duration TEXT, dependencies TEXT,
                status TEXT, micro_action TEXT, waiting_for TEXT, notes TEXT,
                embodiment_flag INTEGER, duration_minutes INTEGER,
                cognitive_load TEXT, deferred_until TEXT, archived INTEGER,
                recurrence_interval INTEGER, recurrence_unit TEXT,
                recurrence_anchor TEXT, recurrence_series_id TEXT,
                recurrence_day INTEGER, recurrence_source_id INTEGER,
                completed_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX idx_tasks_recurrence_source
            ON tasks(recurrence_source_id) WHERE recurrence_source_id IS NOT NULL
            """
        )
        connection.execute(
            """
            INSERT INTO tasks
            (id, title, project, category, priority, start_date, deadline, status,
             waiting_for, archived, recurrence_interval, recurrence_unit,
             recurrence_anchor, recurrence_series_id, recurrence_day)
            VALUES (1, 'Staub wischen', 'Haushalt', 'Haushalt', 3,
                    '2026-10-13', '2026-10-20', 'To Do', 'Termin', 0,
                    4, 'weeks', 'due', 'serie-1', 20)
            """
        )

        first = complete_task(connection, 1, completed_on=date(2026, 10, 18))
        second = complete_task(connection, 1, completed_on=date(2026, 10, 18))
        successor = connection.execute(
            "SELECT * FROM tasks WHERE id=?", (first["created_id"],)
        ).fetchone()

        self.assertEqual(connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 2)
        self.assertEqual(second["created_id"], first["created_id"])
        self.assertEqual(successor["project"], "Haushalt")
        self.assertEqual(successor["status"], "To Do")
        self.assertEqual(successor["start_date"], "2026-11-10")
        self.assertEqual(successor["deadline"], "2026-11-17")
        self.assertEqual(successor["waiting_for"], "")
        self.assertEqual(successor["recurrence_source_id"], 1)
        connection.close()

    def test_fixed_recurrence_skips_missed_dates_and_completion_anchor_uses_completion(self):
        fixed = {
            "start_date": "2026-09-24",
            "deadline": "2026-10-01",
            "recurrence_interval": 1,
            "recurrence_unit": "weeks",
            "recurrence_anchor": "due",
            "recurrence_day": 1,
        }
        fixed_start, fixed_deadline = next_occurrence_dates(
            fixed, completed_on=date(2026, 10, 20)
        )
        self.assertEqual(fixed_start, date(2026, 10, 15))
        self.assertEqual(fixed_deadline, date(2026, 10, 22))

        after_completion = {
            "start_date": "2026-01-24",
            "deadline": "2026-01-31",
            "recurrence_interval": 1,
            "recurrence_unit": "months",
            "recurrence_anchor": "completion",
            "recurrence_day": 31,
        }
        completion_start, completion_deadline = next_occurrence_dates(
            after_completion, completed_on=date(2026, 2, 10)
        )
        self.assertEqual(completion_start, date(2026, 3, 3))
        self.assertEqual(completion_deadline, date(2026, 3, 10))

    def test_parse_duration_minutes_accepts_explicit_units(self):
        self.assertEqual(parse_duration_minutes("30 min"), 30)
        self.assertEqual(parse_duration_minutes("1,5 h"), 90)
        self.assertEqual(parse_duration_minutes("02:15"), 135)
        self.assertIsNone(parse_duration_minutes("2 Tage"))

    def test_dependencies_require_all_referenced_tasks_to_be_done(self):
        statuses = {1: "Done", 2: "In Progress"}
        self.assertTrue(dependency_is_done("1", statuses))
        self.assertFalse(dependency_is_done("1,2", statuses))
        self.assertTrue(dependency_is_done("", statuses))

    def test_available_now_combines_all_conditions(self):
        tasks = pd.DataFrame(
            [
                {"id": 1, "status": "Done", "start_date": None, "deferred_until": None, "waiting_for": "", "dependencies": "", "archived": 0},
                {"id": 2, "status": "To Do", "start_date": "2026-10-01", "deferred_until": None, "waiting_for": "", "dependencies": "1", "archived": 0},
                {"id": 3, "status": "To Do", "start_date": "2026-10-13", "deferred_until": None, "waiting_for": "", "dependencies": "", "archived": 0},
                {"id": 4, "status": "To Do", "start_date": None, "deferred_until": None, "waiting_for": "Antwort", "dependencies": "", "archived": 0},
                {"id": 5, "status": "In Progress", "start_date": None, "deferred_until": None, "waiting_for": "", "dependencies": "", "archived": 0},
                {"id": 6, "status": "To Do", "start_date": None, "deferred_until": "2026-10-13", "waiting_for": "", "dependencies": "", "archived": 0},
            ]
        )
        mask = available_now_mask(tasks, today=date(2026, 10, 12))
        self.assertEqual(tasks.loc[mask, "id"].tolist(), [2, 5])

    def test_task_hint_explains_blocking_reason(self):
        row = {
            "status": "To Do",
            "archived": 0,
            "deferred_until": None,
            "waiting_for": "",
            "dependencies": "7",
            "start_date": None,
            "deadline": None,
        }
        self.assertEqual(
            task_hint(row, {7: "To Do"}, today=date(2026, 10, 12)),
            "Blockiert durch Task 7",
        )

    def test_task_text_search_combines_terms_across_fields(self):
        tasks = pd.DataFrame(
            [
                {
                    "id": 1,
                    "title": "Laptop reparieren",
                    "project": "Hardware",
                    "category": "Sonstiges",
                    "core_focus": "Keiner",
                    "status": "In Progress",
                    "micro_action": "Diagnose prüfen",
                    "waiting_for": "",
                    "notes": "Garantieunterlagen suchen",
                },
                {
                    "id": 2,
                    "title": "Seminar vorbereiten",
                    "project": "Studium",
                    "category": "Studium",
                    "core_focus": "Control",
                    "status": "To Do",
                    "micro_action": "Gliederung schreiben",
                    "waiting_for": "",
                    "notes": "",
                },
            ]
        )

        mask = task_text_search_mask(tasks, "laptop garantie")

        self.assertEqual(tasks.loc[mask, "id"].tolist(), [1])

    def test_timeline_filter_includes_intervals_that_overlap_the_period(self):
        timeline = pd.DataFrame(
            [
                {"id": 1, "start": "2026-09-01", "end": "2026-10-12"},
                {"id": 2, "start": "2026-10-10", "end": "2026-10-20"},
                {"id": 3, "start": "2026-11-01", "end": "2026-11-10"},
                {"id": 4, "start": "2026-08-01", "end": "2026-08-10"},
            ]
        )
        mask = timeline_overlap_mask(
            timeline,
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
        )
        self.assertEqual(timeline.loc[mask, "id"].tolist(), [1, 2])

    def test_timeline_excludes_done_and_archived_tasks(self):
        tasks = pd.DataFrame(
            [
                {"id": 1, "status": "To Do", "archived": 0},
                {"id": 2, "status": "Done", "archived": 0},
                {"id": 3, "status": "In Progress", "archived": 1},
                {"id": 4, "status": "Warte", "archived": None},
            ]
        )

        mask = timeline_task_mask(tasks)

        self.assertEqual(tasks.loc[mask, "id"].tolist(), [1, 4])

    def test_dependency_alignment_never_extends_the_stored_deadline(self):
        timeline = pd.DataFrame(
            [
                {
                    "id": 50,
                    "dependencies": "",
                    "start": pd.Timestamp("2026-10-12"),
                    "end": pd.Timestamp("2026-10-13"),
                },
                {
                    "id": 39,
                    "dependencies": "50",
                    "start": pd.Timestamp("2026-03-27"),
                    "end": pd.Timestamp("2026-10-31"),
                },
            ]
        )

        result = align_timeline_starts_with_dependencies(timeline)

        task = result[result["id"] == 39].iloc[0]
        self.assertEqual(task["start"], pd.Timestamp("2026-10-13"))
        self.assertEqual(task["end"], pd.Timestamp("2026-10-31"))

    def test_csv_import_understands_german_headers_and_defaults(self):
        raw = read_csv_bytes(
            "Titel;Projekt;Priorität;Dauer;Kognitive Belastung\n"
            "Kurz prüfen;Inbox;2;0,5 h;Niedrig\n".encode("utf-8-sig")
        )
        result = normalize_import_data(raw)
        self.assertEqual(result.loc[0, "title"], "Kurz prüfen")
        self.assertEqual(result.loc[0, "project"], "Inbox")
        self.assertEqual(result.loc[0, "priority"], 2)
        self.assertEqual(result.loc[0, "duration_minutes"], 30)
        self.assertEqual(result.loc[0, "status"], "To Do")
        self.assertEqual(result.loc[0, "errors"], "")

    def test_csv_import_reports_invalid_rows_without_guessing(self):
        raw = pd.DataFrame([{"Titel": "", "Priorität": "9", "Dauer_Minuten": "12,5"}])
        errors = normalize_import_data(raw).loc[0, "errors"]
        self.assertIn("Titel fehlt", errors)
        self.assertIn("Priorität muss zwischen 1 und 5 liegen", errors)
        self.assertIn("Dauer in Minuten muss eine positive ganze Zahl sein", errors)

    def test_id_update_aliases_are_normalized_without_new_task_defaults(self):
        raw = pd.DataFrame(
            [
                {
                    "ID": "12",
                    "Titel": "Bestehender Task",
                    "Neuer_Status": "Done",
                    "Neue_Priorität": "1",
                    "Neue_Deadline": "",
                    "Kommentar": "erledigt",
                }
            ]
        )
        result = normalize_import_data(raw)
        self.assertEqual(result.loc[0, "id"], 12)
        self.assertEqual(result.loc[0, "action"], "Aktualisieren")
        self.assertEqual(result.loc[0, "status"], "Done")
        self.assertEqual(result.loc[0, "priority"], 1)
        self.assertIsNone(result.loc[0, "deadline"])
        self.assertIn("comment", result.attrs["provided_fields"])

    def test_id_and_title_are_checked_against_existing_tasks(self):
        raw = pd.DataFrame([{"ID": "5", "Titel": "Falscher Titel", "Status": "Done"}])
        normalized = normalize_import_data(raw)
        existing = pd.DataFrame([{"id": 5, "title": "Richtiger Titel"}])
        result = classify_import_data(normalized, existing)
        self.assertIn("Titel stimmt nicht mit ID 5 überein", result.loc[0, "errors"])

    def test_id_update_changes_only_provided_fields_and_appends_comment(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            CREATE TABLE tasks (
                id INTEGER PRIMARY KEY, title TEXT, project TEXT, category TEXT,
                core_focus TEXT, priority INTEGER, start_date TEXT, deadline TEXT,
                duration TEXT, dependencies TEXT, status TEXT, micro_action TEXT,
                waiting_for TEXT, notes TEXT, embodiment_flag INTEGER,
                duration_minutes INTEGER, cognitive_load TEXT,
                deferred_until TEXT, archived INTEGER,
                recurrence_interval INTEGER, recurrence_unit TEXT,
                recurrence_anchor TEXT, recurrence_series_id TEXT,
                recurrence_day INTEGER, recurrence_source_id INTEGER,
                completed_at TEXT
            )
            """
        )
        connection.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT UNIQUE, active INTEGER DEFAULT 1)"
        )
        connection.execute(
            """
            INSERT INTO tasks
            (id, title, project, category, priority, deadline, status, micro_action,
             waiting_for, notes, archived)
            VALUES (5, 'Richtiger Titel', 'Alt', 'Studium', 3, '2026-10-20',
                    'To Do', 'Alt', 'Antwort', 'Bestehende Notiz', 0)
            """
        )
        raw = pd.DataFrame(
            [
                {
                    "ID": "5",
                    "Titel": "Richtiger Titel",
                    "Neuer_Status": "Done",
                    "Neue_Priorität": "1",
                    "Neue_Deadline": "",
                    "Neuer_Nächster_Schritt": "",
                    "Neues_Warte_auf": "",
                    "Kommentar": "erledigt",
                }
            ]
        )
        normalized = normalize_import_data(raw)
        existing = pd.read_sql_query("SELECT * FROM tasks", connection)
        classified = classify_import_data(normalized, existing)
        result = apply_task_import(connection, classified)
        updated = connection.execute("SELECT * FROM tasks WHERE id=5").fetchone()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(updated["status"], "Done")
        self.assertEqual(updated["priority"], 1)
        self.assertIsNone(updated["deadline"])
        self.assertEqual(updated["micro_action"], "")
        self.assertEqual(updated["waiting_for"], "")
        self.assertEqual(updated["project"], "Alt")
        self.assertIn("Bestehende Notiz", updated["notes"])
        self.assertIn("CSV-Kommentar: erledigt", updated["notes"])
        connection.close()


if __name__ == "__main__":
    unittest.main()
