"""Transactional CSV inserts and ID-based task updates."""

import pandas as pd

from utils.recurrence import complete_task


UPDATE_FIELDS = {
    "title",
    "project",
    "category",
    "core_focus",
    "priority",
    "start_date",
    "deadline",
    "duration",
    "dependencies",
    "status",
    "micro_action",
    "waiting_for",
    "notes",
    "embodiment_flag",
    "duration_minutes",
    "cognitive_load",
    "deferred_until",
    "archived",
}

NONE_IF_BLANK = {
    "project",
    "start_date",
    "deadline",
    "duration_minutes",
    "cognitive_load",
    "deferred_until",
}


def _value(record, field):
    value = record.get(field)
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None if field in NONE_IF_BLANK else ""
    if isinstance(value, str):
        value = value.strip()
        if not value and field in NONE_IF_BLANK:
            return None
    return value


def _notes_with_comment(notes, comment):
    base = str(notes or "").strip()
    clean_comment = str(comment or "").strip()
    if not clean_comment:
        return base
    line = f"CSV-Kommentar: {clean_comment}"
    if line.casefold() in base.casefold():
        return base
    return f"{base}\n{line}".strip()


def apply_task_import(connection, import_data, skip_duplicates=True):
    """Apply validated imports in the caller's transaction."""
    if import_data.empty:
        return {"inserted": 0, "updated": 0, "skipped": 0}
    invalid = import_data[import_data["errors"].fillna("").ne("")]
    if not invalid.empty:
        raise ValueError("Importdaten enthalten noch Fehler")

    provided_fields = set(import_data.attrs.get("provided_fields", []))
    existing_rows = {
        int(row["id"]): dict(row)
        for row in connection.execute("SELECT * FROM tasks").fetchall()
    }
    existing_keys = {
        (
            str(row["title"] or "").strip().casefold(),
            str(row["project"] or "").strip().casefold(),
        )
        for row in existing_rows.values()
    }
    inserted = updated = skipped = 0

    for record in import_data.to_dict("records"):
        task_id = record.get("id")
        if task_id is not None and not pd.isna(task_id):
            task_id = int(task_id)
            existing = existing_rows[task_id]
            changes = {}
            for field in provided_fields & UPDATE_FIELDS:
                value = _value(record, field)
                if field in {"title", "status", "priority"} and value in (None, ""):
                    continue
                changes[field] = value

            if "comment" in provided_fields:
                base_notes = changes.get("notes", existing.get("notes"))
                changes["notes"] = _notes_with_comment(base_notes, record.get("comment"))

            project = changes.get("project")
            if project:
                connection.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (project,))
            if changes:
                assignments = ", ".join(f"{field}=?" for field in changes)
                connection.execute(
                    f"UPDATE tasks SET {assignments} WHERE id=?",
                    (*changes.values(), task_id),
                )
                if changes.get("status") == "Done" and existing.get("status") != "Done":
                    complete_task(connection, task_id)
                updated += 1
            else:
                skipped += 1
            continue

        title = str(record.get("title") or "").strip()
        project = str(record.get("project") or "").strip()
        key = (title.casefold(), project.casefold())
        if skip_duplicates and key in existing_keys:
            skipped += 1
            continue
        if project:
            connection.execute("INSERT OR IGNORE INTO projects (name) VALUES (?)", (project,))
        notes = _notes_with_comment(record.get("notes"), record.get("comment"))
        connection.execute(
            """
            INSERT INTO tasks
            (title, project, category, core_focus, priority, start_date, deadline,
             duration, dependencies, status, micro_action, waiting_for, notes,
             embodiment_flag, duration_minutes, cognitive_load, deferred_until, archived)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                project or None,
                record.get("category") or "Sonstiges",
                record.get("core_focus") or "Keiner",
                record.get("priority") or 3,
                record.get("start_date"),
                record.get("deadline"),
                record.get("duration") or "",
                record.get("dependencies") or "",
                record.get("status") or "To Do",
                record.get("micro_action") or "",
                record.get("waiting_for") or "",
                notes,
                int(record.get("embodiment_flag") or 0),
                record.get("duration_minutes"),
                record.get("cognitive_load"),
                record.get("deferred_until"),
                int(record.get("archived") or 0),
            ),
        )
        existing_keys.add(key)
        inserted += 1

    return {"inserted": inserted, "updated": updated, "skipped": skipped}
