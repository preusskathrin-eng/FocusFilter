"""Create a small, anonymous FocusFilter example database."""

import argparse
from datetime import date, timedelta
import os
from pathlib import Path
import sqlite3
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_DIR / "examples" / "tasks.example.db"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--force", action="store_true", help="Vorhandene Datei ersetzen")
    args = parser.parse_args()

    output = args.output.resolve()
    if output.exists() and not args.force:
        raise SystemExit(f"Datei existiert bereits: {output} (mit --force ersetzen)")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    os.environ["TASK_PLANNER_DB_PATH"] = str(output)
    os.environ["TASK_PLANNER_BACKUP_DIR"] = str(output.parent / "_unused_backups")
    sys.path.insert(0, str(PROJECT_DIR))

    from app_shared import init_db  # noqa: E402

    init_db()
    today = date.today()
    week_start = today - timedelta(days=today.weekday())

    tasks = [
        {
            "id": 1,
            "title": "Projektstruktur festlegen",
            "project": "Beispielprojekt",
            "category": "Sonstiges",
            "core_focus": "Control",
            "priority": 1,
            "start_date": (today - timedelta(days=5)).isoformat(),
            "deadline": (today - timedelta(days=2)).isoformat(),
            "duration": "30 Min.",
            "duration_minutes": 30,
            "dependencies": "",
            "status": "Done",
            "micro_action": "Ordner und Zuständigkeiten notieren",
            "waiting_for": "",
            "notes": "Anonymes Beispiel für eine abgeschlossene Aufgabe.",
            "cognitive_load": "Niedrig",
            "completed_at": (today - timedelta(days=1)).isoformat(),
        },
        {
            "id": 2,
            "title": "Kapitelentwurf überarbeiten",
            "project": "Beispielprojekt",
            "category": "Studium",
            "core_focus": "Control",
            "priority": 1,
            "start_date": today.isoformat(),
            "deadline": (today + timedelta(days=3)).isoformat(),
            "duration": "45 Min.",
            "duration_minutes": 45,
            "dependencies": "1",
            "status": "In Progress",
            "micro_action": "Die erste markierte Passage überarbeiten",
            "waiting_for": "",
            "notes": "",
            "cognitive_load": "Mittel",
        },
        {
            "id": 3,
            "title": "Küche gründlich reinigen",
            "project": "Haushalt",
            "category": "Haushalt",
            "core_focus": "Embodiment",
            "priority": 3,
            "start_date": today.isoformat(),
            "deadline": (today + timedelta(days=5)).isoformat(),
            "duration": "30 Min.",
            "duration_minutes": 30,
            "dependencies": "",
            "status": "To Do",
            "micro_action": "Arbeitsflächen freiräumen",
            "waiting_for": "",
            "notes": "Wiederkehrendes Beispiel im festen Zwei-Wochen-Rhythmus.",
            "cognitive_load": "Niedrig",
            "recurrence_interval": 2,
            "recurrence_unit": "weeks",
            "recurrence_anchor": "due",
            "recurrence_series_id": "demo-haushalt-001",
            "recurrence_day": (today + timedelta(days=5)).day,
        },
        {
            "id": 4,
            "title": "Rückmeldung zum Entwurf abwarten",
            "project": "Organisation",
            "category": "Sonstiges",
            "core_focus": "Keiner",
            "priority": 2,
            "start_date": today.isoformat(),
            "deadline": (today + timedelta(days=7)).isoformat(),
            "duration": "10 Min.",
            "duration_minutes": 10,
            "dependencies": "",
            "status": "Warte",
            "micro_action": "Nach Eingang der Antwort nächsten Schritt festlegen",
            "waiting_for": "Antwort per E-Mail",
            "notes": "",
            "cognitive_load": "Niedrig",
        },
        {
            "id": 5,
            "title": "Ideen für ein Nebenprojekt sammeln",
            "project": "Persönlich",
            "category": "Hobby",
            "core_focus": "Regulation",
            "priority": 4,
            "start_date": (today + timedelta(days=2)).isoformat(),
            "deadline": None,
            "duration": "20 Min.",
            "duration_minutes": 20,
            "dependencies": "",
            "status": "To Do",
            "micro_action": "Drei ungefilterte Ideen notieren",
            "waiting_for": "",
            "notes": "Beispiel für eine Aufgabe mit zukünftigem Startdatum.",
            "cognitive_load": "Niedrig",
        },
    ]

    task_columns = [
        "id", "title", "project", "category", "core_focus", "priority",
        "start_date", "deadline", "duration", "dependencies", "status",
        "micro_action", "waiting_for", "notes", "embodiment_flag",
        "duration_minutes", "cognitive_load", "deferred_until", "archived",
        "recurrence_interval", "recurrence_unit", "recurrence_anchor",
        "recurrence_series_id", "recurrence_day", "recurrence_source_id",
        "completed_at",
    ]
    placeholders = ", ".join("?" for _ in task_columns)
    sql = f"INSERT INTO tasks ({', '.join(task_columns)}) VALUES ({placeholders})"

    connection = sqlite3.connect(output)
    try:
        for task in tasks:
            defaults = {"embodiment_flag": 0, "archived": 0}
            values = [task.get(column, defaults.get(column)) for column in task_columns]
            connection.execute(sql, values)
        connection.executemany(
            "INSERT INTO projects (name) VALUES (?)",
            [(name,) for name in ("Beispielprojekt", "Haushalt", "Organisation", "Persönlich")],
        )
        connection.executemany(
            """
            INSERT INTO weekly_reviews (week_start, task_id, outcome, note)
            VALUES (?, ?, ?, ?)
            """,
            [
                (week_start.isoformat(), 1, "Erledigt", "Grundstruktur steht."),
                (week_start.isoformat(), 2, "Fortschritt gemacht", "Ersten Abschnitt überarbeitet."),
            ],
        )
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"SQLite integrity_check: {integrity}")
    finally:
        connection.close()

    print(f"Beispieldatenbank erstellt: {output}")
    print(f"Tasks: {len(tasks)}, Projekte: 4, Reviews: 2, integrity: ok")


if __name__ == "__main__":
    main()
