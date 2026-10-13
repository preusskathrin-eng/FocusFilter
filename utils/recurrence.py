"""Recurrence rules and transactional completion of task occurrences."""

from calendar import monthrange
from datetime import date, timedelta
import uuid

import pandas as pd


RECURRENCE_PRESETS = [
    "Nicht wiederkehrend",
    "Täglich",
    "Wöchentlich",
    "Alle 2 Wochen",
    "Alle 4 Wochen",
    "Monatlich",
    "Benutzerdefiniert",
]
RECURRENCE_UNITS = {"Tage": "days", "Wochen": "weeks", "Monate": "months"}
RECURRENCE_UNIT_LABELS = {value: label for label, value in RECURRENCE_UNITS.items()}
RECURRENCE_ANCHORS = {
    "Nach ursprünglicher Fälligkeit": "due",
    "Nach Erledigung": "completion",
}
RECURRENCE_ANCHOR_LABELS = {value: label for label, value in RECURRENCE_ANCHORS.items()}

_PRESET_VALUES = {
    "Täglich": (1, "days"),
    "Wöchentlich": (1, "weeks"),
    "Alle 2 Wochen": (2, "weeks"),
    "Alle 4 Wochen": (4, "weeks"),
    "Monatlich": (1, "months"),
}


def recurrence_interval_value(value, default=None):
    """Return a persisted interval as int while treating pandas NA as empty."""
    if value is None or pd.isna(value):
        return default
    if isinstance(value, str) and not value.strip():
        return default
    return int(value)


def recurrence_text_value(value, default=None):
    """Return a persisted recurrence text while treating pandas NA as empty."""
    if value is None or pd.isna(value):
        return default
    text = str(value).strip()
    return text or default


def recurrence_config(preset, custom_interval=1, custom_unit_label="Wochen"):
    """Convert a UI preset to persisted interval and unit values."""
    if preset == "Nicht wiederkehrend":
        return None, None
    if preset == "Benutzerdefiniert":
        return int(custom_interval), RECURRENCE_UNITS[custom_unit_label]
    return _PRESET_VALUES[preset]


def recurrence_preset(interval, unit):
    """Return the closest UI preset for persisted recurrence fields."""
    interval = recurrence_interval_value(interval)
    unit = recurrence_text_value(unit)
    if interval is None or unit is None:
        return "Nicht wiederkehrend"
    value = (interval, unit)
    for label, preset_value in _PRESET_VALUES.items():
        if value == preset_value:
            return label
    return "Benutzerdefiniert"


def recurrence_label(row):
    """Return a concise German recurrence description for a task row."""
    interval = recurrence_interval_value(row.get("recurrence_interval"))
    unit = recurrence_text_value(row.get("recurrence_unit"))
    if interval is None or unit is None:
        return ""
    preset = recurrence_preset(interval, unit)
    if preset == "Benutzerdefiniert":
        unit_label = RECURRENCE_UNIT_LABELS.get(unit, unit)
        schedule = f"Alle {interval} {unit_label}"
    else:
        schedule = preset
    anchor = RECURRENCE_ANCHOR_LABELS.get(
        recurrence_text_value(row.get("recurrence_anchor"), "due"),
        "Nach ursprünglicher Fälligkeit",
    )
    return f"{schedule} · {anchor.lower()}"


def add_recurrence_interval(value, interval, unit, preferred_day=None):
    """Advance a date while preserving a monthly series' preferred day."""
    current = pd.Timestamp(value).date()
    interval = int(interval)
    if unit == "days":
        return current + timedelta(days=interval)
    if unit == "weeks":
        return current + timedelta(weeks=interval)
    if unit != "months":
        raise ValueError(f"Unbekannte Wiederholungseinheit: {unit}")

    month_index = current.year * 12 + current.month - 1 + interval
    year, month_zero_based = divmod(month_index, 12)
    month = month_zero_based + 1
    day = min(int(preferred_day or current.day), monthrange(year, month)[1])
    return date(year, month, day)


def next_occurrence_dates(task, completed_on=None):
    """Calculate the next start and deadline for a recurring task."""
    deadline = pd.to_datetime(task.get("deadline"), errors="coerce")
    if pd.isna(deadline):
        raise ValueError("Wiederkehrende Aufgaben benötigen eine Deadline.")
    deadline = deadline.date()

    completed_on = completed_on or date.today()
    anchor = task.get("recurrence_anchor") or "due"
    base_date = completed_on if anchor == "completion" else deadline
    preferred_day = (
        completed_on.day
        if anchor == "completion"
        else task.get("recurrence_day") or deadline.day
    )
    next_deadline = add_recurrence_interval(
        base_date,
        int(task["recurrence_interval"]),
        task["recurrence_unit"],
        preferred_day=preferred_day,
    )
    while anchor == "due" and next_deadline <= completed_on:
        next_deadline = add_recurrence_interval(
            next_deadline,
            int(task["recurrence_interval"]),
            task["recurrence_unit"],
            preferred_day=preferred_day,
        )

    start = pd.to_datetime(task.get("start_date"), errors="coerce")
    next_start = None
    if pd.notna(start):
        lead_days = max((deadline - start.date()).days, 0)
        next_start = next_deadline - timedelta(days=lead_days)
    return next_start, next_deadline


def complete_task(connection, task_id, completed_on=None):
    """Mark one occurrence done and create at most one recurring successor."""
    completed_on = completed_on or date.today()
    task = connection.execute("SELECT * FROM tasks WHERE id=?", (int(task_id),)).fetchone()
    if task is None:
        raise ValueError(f"Task {task_id} wurde nicht gefunden.")
    task = dict(task)

    connection.execute(
        """
        UPDATE tasks
        SET status='Done', completed_at=COALESCE(completed_at, ?)
        WHERE id=?
        """,
        (completed_on.isoformat(), int(task_id)),
    )

    interval = task.get("recurrence_interval")
    unit = task.get("recurrence_unit")
    if interval in (None, "") or not unit:
        return {"completed_id": int(task_id), "created_id": None}

    existing = connection.execute(
        "SELECT id FROM tasks WHERE recurrence_source_id=?",
        (int(task_id),),
    ).fetchone()
    if existing is not None:
        return {"completed_id": int(task_id), "created_id": int(existing["id"])}

    next_start, next_deadline = next_occurrence_dates(task, completed_on=completed_on)
    series_id = task.get("recurrence_series_id") or uuid.uuid4().hex
    recurrence_day = task.get("recurrence_day") or pd.Timestamp(task["deadline"]).day
    connection.execute(
        """
        UPDATE tasks
        SET recurrence_series_id=?, recurrence_day=?
        WHERE id=?
        """,
        (series_id, int(recurrence_day), int(task_id)),
    )
    cursor = connection.execute(
        """
        INSERT INTO tasks
        (title, project, category, core_focus, priority, start_date, deadline,
         duration, dependencies, status, micro_action, waiting_for, notes,
         embodiment_flag, duration_minutes, cognitive_load, deferred_until, archived,
         recurrence_interval, recurrence_unit, recurrence_anchor,
         recurrence_series_id, recurrence_day, recurrence_source_id, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'To Do', ?, '', ?, ?, ?, ?, NULL, 0,
                ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            task["title"], task.get("project"), task["category"], task.get("core_focus"),
            task.get("priority"), next_start.isoformat() if next_start else None,
            next_deadline.isoformat(), task.get("duration"), task.get("dependencies") or "",
            task.get("micro_action") or "", task.get("notes") or "",
            int(task.get("embodiment_flag") or 0), task.get("duration_minutes"),
            task.get("cognitive_load"), int(interval), unit,
            task.get("recurrence_anchor") or "due", series_id, int(recurrence_day),
            int(task_id),
        ),
    )
    return {"completed_id": int(task_id), "created_id": int(cursor.lastrowid)}
