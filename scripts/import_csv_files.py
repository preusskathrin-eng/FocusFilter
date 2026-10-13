"""Validate and import one or more task CSV files transactionally."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from app_shared import DB_PATH, create_timestamped_backup  # noqa: E402
from utils.task_importer import apply_task_import  # noqa: E402
from utils.task_logic import (  # noqa: E402
    classify_import_data,
    normalize_import_data,
    read_csv_bytes,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--backup-label", default="before-csv-import")
    args = parser.parse_args()

    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    batches = []
    for path in args.files:
        raw = read_csv_bytes(path.read_bytes())
        normalized = normalize_import_data(raw)
        existing = pd.read_sql_query("SELECT * FROM tasks ORDER BY id", connection)
        classified = classify_import_data(normalized, existing)
        invalid = classified[classified["errors"].fillna("").ne("")]
        if not invalid.empty:
            details = invalid[["source_row", "id", "title", "errors"]].to_dict("records")
            connection.close()
            raise SystemExit(
                json.dumps({"file": str(path), "errors": details}, ensure_ascii=False)
            )
        batches.append((path, classified))

    backup = create_timestamped_backup(args.backup_label)
    results = []
    try:
        connection.execute("BEGIN")
        for path, data in batches:
            result = apply_task_import(connection, data, skip_duplicates=True)
            results.append({"file": str(path), **result})
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    summary = {
        "backup": str(backup),
        "results": results,
        "tasks": connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0],
        "projects": connection.execute("SELECT COUNT(*) FROM projects").fetchone()[0],
        "commented_tasks": connection.execute(
            "SELECT COUNT(*) FROM tasks WHERE notes LIKE ?", ("%CSV-Kommentar:%",)
        ).fetchone()[0],
        "integrity": connection.execute("PRAGMA integrity_check").fetchone()[0],
    }
    connection.close()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
