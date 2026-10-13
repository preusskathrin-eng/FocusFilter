"""Back up and migrate the FocusFilter database for recurring tasks."""

import sqlite3

from app_shared import DB_PATH, create_timestamped_backup, init_db


def main():
    backup_path = create_timestamped_backup("before-recurrence-migration")
    init_db()
    with sqlite3.connect(DB_PATH) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()
        }
        task_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    required = {
        "recurrence_interval",
        "recurrence_unit",
        "recurrence_anchor",
        "recurrence_series_id",
        "recurrence_day",
        "recurrence_source_id",
        "completed_at",
    }
    missing = sorted(required - columns)
    if integrity != "ok" or missing:
        raise RuntimeError(f"Migration fehlgeschlagen: integrity={integrity}, missing={missing}")
    print(f"backup={backup_path}")
    print(f"integrity={integrity}")
    print(f"tasks={task_count}")


if __name__ == "__main__":
    main()
