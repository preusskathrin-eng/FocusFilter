from contextlib import contextmanager
from datetime import date, datetime, timedelta
import os
from pathlib import Path
import re
import sqlite3
import uuid

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.task_logic import (
    align_timeline_starts_with_dependencies,
    available_now_mask,
    classify_import_data,
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
    RECURRENCE_ANCHORS,
    RECURRENCE_PRESETS,
    RECURRENCE_UNIT_LABELS,
    RECURRENCE_UNITS,
    complete_task,
    recurrence_config,
    recurrence_interval_value,
    recurrence_label,
    recurrence_preset,
    recurrence_text_value,
)

APP_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("TASK_PLANNER_DB_PATH", APP_DIR / "tasks.db"))
BACKUP_DIR = Path(os.environ.get("TASK_PLANNER_BACKUP_DIR", APP_DIR / "backups"))
STATUSES = ["To Do", "In Progress", "Warte", "Done"]
CATEGORIES = ["Arbeit", "Studium", "Haushalt", "Organisation", "Hobby", "Sonstiges"]
CORE_OPTIONS = ["Control", "Regulation", "Embodiment", "Keiner"]
COGNITIVE_LEVELS = ["Niedrig", "Mittel", "Hoch"]
REVIEW_RESULTS = ["Nicht bewertet", "Fortschritt gemacht", "Erledigt"]
NO_PROJECT = "(ohne Projekt)"


@contextmanager
def db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db():
    """Create missing structures and migrate existing project names safely."""
    with db_connection() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                project TEXT,
                category TEXT NOT NULL,
                core_focus TEXT,
                priority INTEGER,
                start_date TEXT,
                deadline TEXT,
                duration TEXT,
                dependencies TEXT,
                status TEXT DEFAULT 'To Do',
                micro_action TEXT,
                waiting_for TEXT,
                notes TEXT,
                embodiment_flag BOOLEAN DEFAULT 0
            )
            """
        )
        task_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        if "duration_minutes" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN duration_minutes INTEGER")
        if "cognitive_load" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN cognitive_load TEXT")
        if "deferred_until" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN deferred_until TEXT")
        if "archived" not in task_columns:
            connection.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        recurrence_columns = {
            "recurrence_interval": "INTEGER",
            "recurrence_unit": "TEXT",
            "recurrence_anchor": "TEXT",
            "recurrence_series_id": "TEXT",
            "recurrence_day": "INTEGER",
            "recurrence_source_id": "INTEGER",
            "completed_at": "TEXT",
        }
        for column, definition in recurrence_columns.items():
            if column not in task_columns:
                connection.execute(f"ALTER TABLE tasks ADD COLUMN {column} {definition}")
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_recurrence_source
            ON tasks(recurrence_source_id)
            WHERE recurrence_source_id IS NOT NULL
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_start TEXT NOT NULL,
                task_id INTEGER NOT NULL,
                outcome TEXT NOT NULL CHECK (outcome IN ('Fortschritt gemacht', 'Erledigt')),
                note TEXT,
                reviewed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (week_start, task_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
            """
        )

        # Backfill only unambiguous minute/hour values; longer free-text values stay untouched.
        for row in connection.execute(
            "SELECT id, duration FROM tasks WHERE duration_minutes IS NULL AND duration IS NOT NULL"
        ).fetchall():
            parsed_minutes = parse_duration_minutes(row["duration"])
            if parsed_minutes is not None:
                connection.execute(
                    "UPDATE tasks SET duration_minutes = ? WHERE id = ?",
                    (parsed_minutes, row["id"]),
                )
        connection.execute(
            """
            INSERT OR IGNORE INTO projects (name)
            SELECT DISTINCT TRIM(project)
            FROM tasks
            WHERE project IS NOT NULL AND TRIM(project) <> ''
            """
        )


def read_tasks():
    with db_connection() as connection:
        return pd.read_sql_query("SELECT * FROM tasks ORDER BY id", connection)


def create_daily_backup():
    """Create one consistent SQLite backup per day."""
    BACKUP_DIR.mkdir(exist_ok=True)
    target = BACKUP_DIR / f"tasks-{date.today().isoformat()}.db"
    if target.exists():
        return target
    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def create_timestamped_backup(label="before-csv-import"):
    """Create a dedicated backup immediately before a bulk change."""
    BACKUP_DIR.mkdir(exist_ok=True)
    safe_label = re.sub(r"[^a-z0-9-]+", "-", label.casefold()).strip("-")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    target = BACKUP_DIR / f"tasks-{safe_label}-{timestamp}.db"
    source = sqlite3.connect(DB_PATH)
    destination = sqlite3.connect(target)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()
    return target


def read_projects(active_only=True):
    query = "SELECT id, name, active FROM projects"
    if active_only:
        query += " WHERE active = 1"
    query += " ORDER BY name COLLATE NOCASE"
    with db_connection() as connection:
        return pd.read_sql_query(query, connection)


def project_names(active_only=True):
    return read_projects(active_only)["name"].tolist()


def monday_of(value):
    return value - timedelta(days=value.weekday())


def read_weekly_reviews(week_start=None):
    query = """
        SELECT wr.week_start, wr.task_id, wr.outcome, wr.note, wr.reviewed_at,
               t.title, t.project
        FROM weekly_reviews wr
        JOIN tasks t ON t.id = wr.task_id
    """
    parameters = []
    if week_start is not None:
        query += " WHERE wr.week_start = ?"
        parameters.append(week_start.isoformat())
    query += " ORDER BY wr.week_start DESC, t.project, t.title"
    with db_connection() as connection:
        return pd.read_sql_query(query, connection, params=parameters)


def parse_date(value, fallback=None):
    if value in (None, "") or pd.isna(value):
        return fallback
    return pd.to_datetime(value).date()


def task_label(row):
    return f"#{row['id']} · {row['title']}"


def recurrence_form_controls(prefix, task=None):
    """Render recurrence fields that work reliably inside a Streamlit form."""
    task = task or {}
    current_preset = recurrence_preset(
        task.get("recurrence_interval"), task.get("recurrence_unit")
    )
    preset = st.selectbox(
        "Wiederholung",
        RECURRENCE_PRESETS,
        index=RECURRENCE_PRESETS.index(current_preset),
        key=f"{prefix}_recurrence_preset",
    )
    custom_columns = st.columns(2)
    with custom_columns[0]:
        custom_interval = st.number_input(
            "Eigenes Intervall",
            min_value=1,
            value=recurrence_interval_value(task.get("recurrence_interval"), 1),
            key=f"{prefix}_recurrence_interval",
            help="Wird nur bei „Benutzerdefiniert“ verwendet.",
        )
    with custom_columns[1]:
        current_unit_label = RECURRENCE_UNIT_LABELS.get(
            recurrence_text_value(task.get("recurrence_unit")), "Wochen"
        )
        custom_unit = st.selectbox(
            "Eigene Einheit",
            list(RECURRENCE_UNITS),
            index=list(RECURRENCE_UNITS).index(current_unit_label),
            key=f"{prefix}_recurrence_unit",
            help="Wird nur bei „Benutzerdefiniert“ verwendet.",
        )
    current_anchor_label = next(
        (
            label for label, value in RECURRENCE_ANCHORS.items()
            if value == recurrence_text_value(task.get("recurrence_anchor"), "due")
        ),
        "Nach ursprünglicher Fälligkeit",
    )
    anchor_label = st.selectbox(
        "Nächsten Termin berechnen",
        list(RECURRENCE_ANCHORS),
        index=list(RECURRENCE_ANCHORS).index(current_anchor_label),
        key=f"{prefix}_recurrence_anchor",
        help=(
            "Nach Fälligkeit hält einen festen Rhythmus. Nach Erledigung beginnt das "
            "Intervall am tatsächlichen Abschlusstag."
        ),
    )
    interval, unit = recurrence_config(preset, custom_interval, custom_unit)
    anchor = RECURRENCE_ANCHORS[anchor_label] if interval is not None else None
    return interval, unit, anchor


def recurrence_storage_values(interval, unit, anchor, deadline, existing_series_id=None):
    """Validate recurrence input and return values ready for SQLite."""
    if interval is None:
        return None, None, None, None, None
    if deadline is None:
        raise ValueError("Wiederkehrende Aufgaben benötigen eine Deadline.")
    series_id = recurrence_text_value(existing_series_id) or uuid.uuid4().hex
    return (
        int(interval),
        unit,
        anchor or "due",
        series_id,
        deadline.day,
    )




@st.dialog("Task bearbeiten", width="large")
def edit_task_dialog(task_id):
    tasks = read_tasks()
    matches = tasks[tasks["id"] == task_id]
    if matches.empty:
        st.error("Task nicht gefunden.")
        return
    task = matches.iloc[0].to_dict()
    projects = project_names()
    project_options = [NO_PROJECT] + projects
    current_project = task["project"] or NO_PROJECT
    if current_project not in project_options:
        project_options.append(current_project)

    dependency_options = {
        task_label(row): int(row["id"])
        for row in tasks.to_dict("records") if int(row["id"]) != int(task_id)
    }
    selected_dependency_ids = {
        int(value) for value in re.findall(r"\d+", str(task["dependencies"] or ""))
    }
    dependency_defaults = [
        label for label, value in dependency_options.items() if value in selected_dependency_ids
    ]

    with st.form(f"edit_task_form_{task_id}"):
        left, right = st.columns(2)
        with left:
            title = st.text_input("Titel", task["title"])
            project = st.selectbox(
                "Projekt", project_options, index=project_options.index(current_project)
            )
            category = st.selectbox(
                "Kategorie", CATEGORIES,
                index=CATEGORIES.index(task["category"]) if task["category"] in CATEGORIES else 0,
            )
            core_focus = st.selectbox(
                "CoRE-Fokus", CORE_OPTIONS,
                index=CORE_OPTIONS.index(task["core_focus"]) if task["core_focus"] in CORE_OPTIONS else 0,
            )
            priority = st.slider("Priorität (1 = kritisch)", 1, 5, int(task["priority"] or 3))
            status = st.selectbox(
                "Status", STATUSES,
                index=STATUSES.index(task["status"]) if task["status"] in STATUSES else 0,
            )
        with right:
            start_date = st.date_input("Startdatum", parse_date(task["start_date"], date.today()))
            deadline = st.date_input("Deadline", parse_date(task["deadline"]))
            duration = st.text_input("Dauer als Freitext", task["duration"] or "")
            duration_minutes = st.number_input(
                "Dauer in Minuten", min_value=1,
                value=int(task["duration_minutes"]) if pd.notna(task["duration_minutes"]) else None,
                step=5,
            )
            cognitive = st.selectbox(
                "Kognitive Belastung", ["Nicht eingestuft"] + COGNITIVE_LEVELS,
                index=(["Nicht eingestuft"] + COGNITIVE_LEVELS).index(task["cognitive_load"])
                if task["cognitive_load"] in COGNITIVE_LEVELS else 0,
            )
            deferred_until = st.date_input(
                "Zurückgestellt bis", parse_date(task["deferred_until"])
            )

        dependencies = st.multiselect(
            "Abhängigkeiten", dependency_options, default=dependency_defaults,
            help="Die Aufgabe gilt erst als machbar, wenn alle ausgewählten Tasks erledigt sind.",
        )
        micro_action = st.text_area("Nächster konkreter Schritt", task["micro_action"] or "")
        waiting_for = st.text_input("Warte auf", task["waiting_for"] or "")
        notes = st.text_area("Notizen", task["notes"] or "")
        st.subheader("Wiederholung")
        recurrence_interval, recurrence_unit, recurrence_anchor = recurrence_form_controls(
            f"edit_task_{task_id}", task
        )
        embodiment = st.checkbox("Braucht Embodiment-/Regulation-Check?", bool(task["embodiment_flag"]))
        archived = st.checkbox("Task archivieren", bool(task["archived"]))

        if st.form_submit_button("Änderungen speichern", type="primary"):
            if not title.strip():
                st.error("Der Titel darf nicht leer sein.")
            else:
                try:
                    recurrence_values = recurrence_storage_values(
                        recurrence_interval,
                        recurrence_unit,
                        recurrence_anchor,
                        deadline,
                        task.get("recurrence_series_id"),
                    )
                except ValueError as error:
                    st.error(str(error))
                else:
                    dependency_ids = ",".join(
                        str(dependency_options[label]) for label in dependencies
                    )
                    with db_connection() as connection:
                        connection.execute(
                            """
                            UPDATE tasks SET title=?, project=?, category=?, core_focus=?,
                                priority=?, status=?, start_date=?, deadline=?, duration=?,
                                duration_minutes=?, cognitive_load=?, dependencies=?, micro_action=?,
                                waiting_for=?, notes=?, embodiment_flag=?, archived=?, deferred_until=?,
                                recurrence_interval=?, recurrence_unit=?, recurrence_anchor=?,
                                recurrence_series_id=?, recurrence_day=?
                            WHERE id=?
                            """,
                            (
                                title.strip(), None if project == NO_PROJECT else project,
                                category, core_focus, priority, status,
                                start_date.isoformat() if start_date else None,
                                deadline.isoformat() if deadline else None,
                                duration.strip(), duration_minutes,
                                None if cognitive == "Nicht eingestuft" else cognitive,
                                dependency_ids, micro_action.strip(), waiting_for.strip(),
                                notes.strip(), int(embodiment), int(archived),
                                deferred_until.isoformat() if deferred_until else None,
                                *recurrence_values, int(task_id),
                            ),
                        )
                        if status == "Done":
                            complete_task(connection, int(task_id))
                        else:
                            connection.execute(
                                "UPDATE tasks SET completed_at=NULL WHERE id=?",
                                (int(task_id),),
                            )
                    st.rerun()
