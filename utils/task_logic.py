"""Datenunabhängige Aufgaben-, Filter- und CSV-Logik."""

from datetime import date
from io import StringIO
import re

import pandas as pd


STATUSES = ["To Do", "In Progress", "Warte", "Done"]
COGNITIVE_LEVELS = ["Niedrig", "Mittel", "Hoch"]
TASK_SEARCH_COLUMNS = [
    "title",
    "project",
    "category",
    "core_focus",
    "status",
    "micro_action",
    "waiting_for",
    "notes",
]

CSV_ALIASES = {
    "id": ["id", "task_id"],
    "title": ["title", "titel", "aufgabe", "task"],
    "project": ["project", "projekt", "projekt_subprojekt"],
    "category": ["category", "kategorie", "hauptkategorie"],
    "core_focus": ["core_focus", "core_fokus", "fokus"],
    "priority": ["priority", "prioritaet", "prio", "neue_prioritaet"],
    "start_date": ["start_date", "startdatum", "start"],
    "deadline": ["deadline", "faellig", "faelligkeit", "neue_deadline"],
    "duration": ["duration", "dauer", "geschaetzte_dauer"],
    "duration_minutes": ["duration_minutes", "dauer_minuten", "minuten"],
    "cognitive_load": ["cognitive_load", "kognitive_belastung", "kognitiv"],
    "dependencies": ["dependencies", "abhaengigkeiten", "abhaengigkeit"],
    "status": ["status", "neuer_status"],
    "micro_action": [
        "micro_action", "naechster_schritt", "naechste_aktion",
        "neuer_naechster_schritt",
    ],
    "waiting_for": ["waiting_for", "warte_auf", "neues_warte_auf"],
    "notes": ["notes", "notizen", "notiz"],
    "embodiment_flag": ["embodiment_flag", "embodiment_check"],
    "deferred_until": ["deferred_until", "zurueckgestellt_bis"],
    "archived": ["archived", "archiviert"],
    "comment": ["comment", "kommentar"],
}


def parse_duration_minutes(value):
    """Parse explicit minutes/hours without guessing the length of a work day."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return max(int(value), 0)
    text = str(value).strip().lower().replace(",", ".")
    if not text:
        return None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(min|mins|minute|minuten)", text)
    if match:
        return round(float(match.group(1)))
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(h|std|std\.|stunde|stunden)", text)
    if match:
        return round(float(match.group(1)) * 60)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if match and int(match.group(2)) < 60:
        return int(match.group(1)) * 60 + int(match.group(2))
    return None


def dependency_is_done(value, status_by_id):
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return True
    dependency = str(value or "").strip()
    if not dependency:
        return True
    ids = [int(item) for item in re.findall(r"\d+", dependency)]
    return bool(ids) and all(status_by_id.get(item) == "Done" for item in ids)


def available_now_mask(tasks, status_by_id=None, today=None):
    """Return a boolean mask for tasks that can be worked on now."""
    current_day = pd.Timestamp(today or date.today())
    starts = pd.to_datetime(tasks["start_date"], errors="coerce")
    if status_by_id is None:
        status_by_id = tasks.set_index("id")["status"].to_dict()
    dependencies_done = tasks["dependencies"].apply(
        lambda value: dependency_is_done(value, status_by_id)
    )
    not_waiting = tasks["waiting_for"].fillna("").str.strip().eq("")
    deferred = pd.to_datetime(tasks["deferred_until"], errors="coerce")
    return (
        tasks["status"].isin(["To Do", "In Progress"])
        & (starts.isna() | starts.le(current_day))
        & (deferred.isna() | deferred.le(current_day))
        & not_waiting
        & dependencies_done
        & tasks["archived"].fillna(0).eq(0)
    )


def task_hint(row, status_by_id, today=None):
    current_day = today or date.today()
    if bool(row.get("archived", 0)):
        return "Archiviert"
    if row.get("status") == "Done":
        return "Erledigt"
    deferred = pd.to_datetime(row.get("deferred_until"), errors="coerce")
    if pd.notna(deferred) and deferred.date() > current_day:
        return f"Zurückgestellt bis {deferred.strftime('%d.%m.%Y')}"
    waiting_for = str(row.get("waiting_for") or "").strip()
    if waiting_for:
        return f"Wartet auf: {waiting_for}"
    dependency = str(row.get("dependencies") or "").strip()
    if dependency and not dependency_is_done(dependency, status_by_id):
        return f"Blockiert durch Task {dependency}"
    start = pd.to_datetime(row.get("start_date"), errors="coerce")
    if pd.notna(start) and start.date() > current_day:
        return f"Start ab {start.strftime('%d.%m.%Y')}"
    deadline = pd.to_datetime(row.get("deadline"), errors="coerce")
    if pd.notna(deadline) and deadline.date() < current_day:
        return f"Überfällig seit {deadline.strftime('%d.%m.%Y')}"
    return "Jetzt machbar"


def timeline_overlap_mask(timeline, start=None, end=None):
    """Return tasks whose start/end interval overlaps the selected period."""
    starts = pd.to_datetime(timeline["start"], errors="coerce")
    ends = pd.to_datetime(timeline["end"], errors="coerce")
    mask = starts.notna() & ends.notna()
    if start is not None:
        mask &= ends.ge(pd.Timestamp(start))
    if end is not None:
        mask &= starts.le(pd.Timestamp(end))
    return mask


def timeline_task_mask(tasks):
    """Return non-archived, unfinished tasks eligible for the timeline."""
    return tasks["archived"].fillna(0).eq(0) & tasks["status"].ne("Done")


def task_text_search_mask(tasks, query):
    """Match every search term across the task's descriptive text fields."""
    terms = str(query or "").casefold().split()
    if not terms:
        return pd.Series(True, index=tasks.index)

    columns = [column for column in TASK_SEARCH_COLUMNS if column in tasks.columns]
    if not columns:
        return pd.Series(False, index=tasks.index)

    haystack = (
        tasks[columns]
        .fillna("")
        .astype(str)
        .agg(" ".join, axis=1)
        .str.casefold()
    )
    mask = pd.Series(True, index=tasks.index)
    for term in terms:
        mask &= haystack.str.contains(term, regex=False, na=False)
    return mask


def align_timeline_starts_with_dependencies(timeline):
    """Move starts behind a dependency without inventing a later deadline."""
    result = timeline.copy()
    for index, row in result.iterrows():
        dependency = str(row.get("dependencies") or "").strip()
        if not dependency.isdigit():
            continue

        parent = result[result["id"] == int(dependency)]
        if parent.empty:
            continue

        parent_end = parent["end"].iloc[0]
        task_start = row.get("start")
        task_end = row.get("end")
        if (
            pd.notna(parent_end)
            and pd.notna(task_end)
            and parent_end <= task_end
            and (pd.isna(task_start) or task_start < parent_end)
        ):
            result.at[index, "start"] = parent_end
    return result


def normalized_header(value):
    text = str(value).strip().casefold()
    text = text.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def read_csv_bytes(data):
    last_error = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = data.decode(encoding)
            return pd.read_csv(
                StringIO(text), sep=None, engine="python", dtype=str, keep_default_na=False
            )
        except (UnicodeDecodeError, pd.errors.ParserError) as error:
            last_error = error
    raise ValueError(f"CSV konnte nicht gelesen werden: {last_error}")


def csv_value(row, normalized_columns, field):
    for alias in CSV_ALIASES[field]:
        original_column = normalized_columns.get(alias)
        if original_column is not None:
            return str(row.get(original_column, "")).strip()
    return ""


def import_field_map(raw):
    """Map canonical import fields to the columns present in a CSV."""
    normalized_columns = {normalized_header(column): column for column in raw.columns}
    return {
        field: normalized_columns[alias]
        for field, aliases in CSV_ALIASES.items()
        for alias in aliases
        if alias in normalized_columns
    }


def import_date(value):
    if not value:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return date.fromisoformat(value).isoformat()
    return pd.to_datetime(value, dayfirst=True, errors="raise").date().isoformat()


def normalize_import_data(raw):
    normalized_columns = {normalized_header(column): column for column in raw.columns}
    provided_fields = set(import_field_map(raw))
    records = []
    seen_ids = set()
    for source_number, (_, row) in enumerate(raw.iterrows(), start=2):
        record = {field: csv_value(row, normalized_columns, field) for field in CSV_ALIASES}
        errors = []
        raw_id = record["id"]
        record["id"] = None
        if raw_id:
            try:
                numeric_id = float(raw_id.replace(",", "."))
                if not numeric_id.is_integer() or numeric_id <= 0:
                    raise ValueError
                record["id"] = int(numeric_id)
                if record["id"] in seen_ids:
                    errors.append(f"ID {record['id']} kommt mehrfach vor")
                seen_ids.add(record["id"])
            except ValueError:
                errors.append("ID muss eine positive ganze Zahl sein")

        is_update = record["id"] is not None
        if not record["title"] and (not is_update or "title" in provided_fields):
            errors.append("Titel fehlt")

        if not is_update:
            record["category"] = record["category"] or "Sonstiges"
            record["core_focus"] = record["core_focus"] or "Keiner"
            record["status"] = record["status"] or "To Do"
        if record["status"] and record["status"] not in STATUSES:
            errors.append(f"Status ungültig: {record['status']}")

        cognitive = record["cognitive_load"].casefold()
        cognitive_map = {item.casefold(): item for item in COGNITIVE_LEVELS}
        record["cognitive_load"] = cognitive_map.get(cognitive) if cognitive else None
        if cognitive and record["cognitive_load"] is None:
            errors.append("Kognitive Belastung muss Niedrig, Mittel oder Hoch sein")

        try:
            priority_value = record["priority"] or (3 if not is_update else None)
            record["priority"] = int(priority_value) if priority_value is not None else None
            if record["priority"] is not None and record["priority"] not in range(1, 6):
                raise ValueError
        except ValueError:
            errors.append("Priorität muss zwischen 1 und 5 liegen")
            record["priority"] = 3

        try:
            minutes = record["duration_minutes"]
            if minutes:
                numeric_minutes = float(minutes.replace(",", "."))
                if not numeric_minutes.is_integer():
                    raise ValueError
                record["duration_minutes"] = int(numeric_minutes)
            else:
                record["duration_minutes"] = parse_duration_minutes(record["duration"])
            if record["duration_minutes"] is not None and record["duration_minutes"] <= 0:
                raise ValueError
        except ValueError:
            errors.append("Dauer in Minuten muss eine positive ganze Zahl sein")
            record["duration_minutes"] = None

        for field, label in (("start_date", "Startdatum"), ("deadline", "Deadline")):
            try:
                record[field] = import_date(record[field])
            except (ValueError, TypeError):
                errors.append(f"{label} ist ungültig")
                record[field] = None

        for field, label in (("deferred_until", "Zurückgestellt bis"),):
            try:
                record[field] = import_date(record[field])
            except (ValueError, TypeError):
                errors.append(f"{label} ist ungültig")
                record[field] = None

        flag = record["embodiment_flag"].casefold()
        record["embodiment_flag"] = int(flag in {"1", "ja", "yes", "true", "x"})
        archived = record["archived"].casefold()
        record["archived"] = int(archived in {"1", "ja", "yes", "true", "x"})
        record["source_row"] = source_number
        record["action"] = "Aktualisieren" if is_update else "Neu"
        record["errors"] = "; ".join(errors)
        records.append(record)
    result = pd.DataFrame(records)
    result.attrs["provided_fields"] = sorted(provided_fields)
    return result


def classify_import_data(import_data, existing_tasks):
    """Validate ID-based updates against the current database snapshot."""
    result = import_data.copy()
    result.attrs.update(import_data.attrs)
    existing_by_id = existing_tasks.set_index("id") if not existing_tasks.empty else pd.DataFrame()
    title_is_provided = "title" in result.attrs.get("provided_fields", [])

    for index, row in result.iterrows():
        task_id = row.get("id")
        if pd.isna(task_id):
            continue
        task_id = int(task_id)
        errors = [item for item in str(row.get("errors") or "").split("; ") if item]
        if existing_tasks.empty or task_id not in existing_by_id.index:
            errors.append(f"ID {task_id} existiert nicht")
        elif title_is_provided:
            expected_title = str(existing_by_id.loc[task_id, "title"] or "").strip()
            supplied_title = str(row.get("title") or "").strip()
            if expected_title.casefold() != supplied_title.casefold():
                errors.append(f"Titel stimmt nicht mit ID {task_id} überein")
        result.at[index, "errors"] = "; ".join(errors)

    return result
