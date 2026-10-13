"""Übersichtsseite von FocusFilter."""

from app_shared import *  # noqa: F403

all_overview_tasks = read_tasks()
search = st.text_input(
    "Aufgaben durchsuchen",
    type="search",
    placeholder="Begriff eingeben, z. B. Projekt, Task oder nächster Schritt",
    help=(
        "Durchsucht Titel, Projekt, Kategorie, Fokus, Status, nächsten Schritt, "
        "„Warte auf“ und Notizen. Mehrere Begriffe können kombiniert werden."
    ),
    key="task_search",
    live="300ms",
)
toolbar = st.columns([1.4, 1, 1])
with toolbar[0]:
    quick_view = st.selectbox(
        "Schnellansicht",
        ["Offene Aufgaben", "Eigene Filter", "Jetzt machbar", "Unter 30 Minuten", "Kognitiv leicht", "Überfällig", "Wartet"],
    )
with toolbar[1]:
    show_archived = st.checkbox("Archivierte anzeigen")
with toolbar[2]:
    st.download_button(
        "Alle Tasks als CSV",
        data=all_overview_tasks.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name=f"focusfilter_export_{date.today().isoformat()}.csv",
        mime="text/csv",
        width="stretch",
    )

tasks = all_overview_tasks.copy()
if not show_archived:
    tasks = tasks[tasks["archived"].fillna(0).eq(0)].copy()
if tasks.empty:
    st.info("Noch keine Tasks vorhanden. Lege auf der Seite „Neuer Task“ den ersten Task an.")
else:
    metric_cols = st.columns(4)
    metric_cols[0].metric("Gesamt", len(tasks))
    metric_cols[1].metric("Offen", int((tasks["status"] == "To Do").sum()))
    metric_cols[2].metric("In Bearbeitung", int((tasks["status"] == "In Progress").sum()))
    metric_cols[3].metric("Erledigt", int((tasks["status"] == "Done").sum()))

    filter_cols = st.columns(3)
    category_options = sorted(tasks["category"].dropna().unique().tolist(), key=str.casefold)
    # Keep projects with existing tasks filterable even if they are inactive.
    project_options = project_names(active_only=False)[:]
    if tasks["project"].isna().any() or tasks["project"].fillna("").str.strip().eq("").any():
        project_options.append(NO_PROJECT)

    with filter_cols[0]:
        category_filter = st.multiselect(
            "Kategorie", category_options, default=[], placeholder="Alle Kategorien"
        )
    with filter_cols[1]:
        project_filter = st.multiselect(
            "Projekt", project_options, default=[], placeholder="Alle Projekte"
        )
    with filter_cols[2]:
        status_filter = st.multiselect(
            "Status", STATUSES, default=[], placeholder="Alle Status"
        )
    with st.expander("Machbarkeit, Aufwand und Sortierung", expanded=False):
        effort_cols = st.columns(4)
        with effort_cols[0]:
            only_available = st.checkbox(
                "Nur jetzt machbare Tasks",
                help=(
                    "Nicht erledigt, Startdatum erreicht, kein Eintrag bei „Warte auf“ "
                    "und alle angegebenen Task-Abhängigkeiten erledigt."
                ),
            )
        with effort_cols[1]:
            deadline_before = st.date_input("Deadline spätestens", value=None)
        with effort_cols[2]:
            max_duration = st.number_input(
                "Max. Dauer in Minuten", min_value=1, value=None, step=5,
                placeholder="z. B. 30",
            )
        with effort_cols[3]:
            cognitive_options = COGNITIVE_LEVELS + ["Nicht eingestuft"]
            cognitive_filter = st.multiselect(
                "Kognitive Belastung", cognitive_options, default=[],
                placeholder="Alle Belastungen",
            )

        sort_order = st.selectbox(
            "Sortieren nach",
            ["Priorität", "Früheste Deadline", "Kürzeste Dauer", "Projekt", "Kognitive Belastung"],
        )

    mask = pd.Series(True, index=tasks.index)
    if category_filter:
        mask &= tasks["category"].isin(category_filter)
    if status_filter:
        mask &= tasks["status"].isin(status_filter)
    if project_filter:
        selected_projects = [value for value in project_filter if value != NO_PROJECT]
        project_mask = tasks["project"].isin(selected_projects)
        if NO_PROJECT in project_filter:
            project_mask |= tasks["project"].isna() | tasks["project"].fillna("").str.strip().eq("")
        mask &= project_mask

    mask &= task_text_search_mask(tasks, search)

    if only_available:
        all_statuses = all_overview_tasks.set_index("id")["status"].to_dict()
        mask &= available_now_mask(tasks, all_statuses)
    if deadline_before:
        deadlines = pd.to_datetime(tasks["deadline"], errors="coerce")
        mask &= deadlines.notna() & deadlines.le(pd.Timestamp(deadline_before))
    if max_duration is not None:
        durations = pd.to_numeric(tasks["duration_minutes"], errors="coerce")
        mask &= durations.notna() & durations.le(int(max_duration))

    if cognitive_filter:
        cognitive_values = tasks["cognitive_load"].fillna("").replace("", "Nicht eingestuft")
        mask &= cognitive_values.isin(cognitive_filter)

    if quick_view == "Offene Aufgaben":
        mask &= tasks["status"].ne("Done")
    elif quick_view == "Jetzt machbar":
        all_statuses = all_overview_tasks.set_index("id")["status"].to_dict()
        mask &= available_now_mask(tasks, all_statuses)
    elif quick_view == "Unter 30 Minuten":
        durations = pd.to_numeric(tasks["duration_minutes"], errors="coerce")
        mask &= durations.notna() & durations.le(30)
    elif quick_view == "Kognitiv leicht":
        mask &= tasks["cognitive_load"].eq("Niedrig")
    elif quick_view == "Überfällig":
        quick_deadlines = pd.to_datetime(tasks["deadline"], errors="coerce")
        mask &= quick_deadlines.notna() & quick_deadlines.lt(pd.Timestamp(date.today())) & tasks["status"].ne("Done")
    elif quick_view == "Wartet":
        mask &= tasks["waiting_for"].fillna("").str.strip().ne("")

    filtered = tasks.loc[mask].copy()
    filtered["start_date"] = pd.to_datetime(filtered["start_date"], errors="coerce").dt.date
    filtered["deadline"] = pd.to_datetime(filtered["deadline"], errors="coerce").dt.date
    status_by_id = all_overview_tasks.set_index("id")["status"].to_dict()
    filtered["hint"] = filtered.apply(lambda row: task_hint(row, status_by_id), axis=1)
    filtered["recurrence"] = filtered.apply(recurrence_label, axis=1)
    if sort_order == "Früheste Deadline":
        sort_columns = ["deadline", "priority", "id"]
    elif sort_order == "Kürzeste Dauer":
        sort_columns = ["duration_minutes", "priority", "id"]
    elif sort_order == "Projekt":
        sort_columns = ["project", "priority", "id"]
    elif sort_order == "Kognitive Belastung":
        load_order = {"Niedrig": 0, "Mittel": 1, "Hoch": 2}
        filtered["_cognitive_order"] = filtered["cognitive_load"].map(load_order).fillna(3)
        sort_columns = ["_cognitive_order", "priority", "id"]
    else:
        sort_columns = ["priority", "deadline", "id"]
    filtered = filtered.sort_values(sort_columns, na_position="last")

    st.caption(f"{len(filtered)} von {len(tasks)} Tasks sichtbar")
    if filtered.empty:
        st.info("Keine Tasks passen zu den gewählten Filtern.")
    else:
        visible_columns = [
            "id", "title", "project", "category", "priority", "start_date", "deadline",
            "status", "duration_minutes", "cognitive_load", "recurrence", "hint",
            "micro_action", "waiting_for"
        ]
        edited = st.data_editor(
            filtered[visible_columns],
            width="stretch",
            hide_index=True,
            disabled=[
                column for column in visible_columns
                if column not in {"status", "priority", "duration_minutes", "cognitive_load"}
            ],
            column_config={
                "id": st.column_config.NumberColumn("ID", width="small"),
                "title": st.column_config.TextColumn("Task", width="large"),
                "project": st.column_config.TextColumn("Projekt"),
                "category": st.column_config.TextColumn("Kategorie"),
                "priority": st.column_config.NumberColumn("Prio", min_value=1, max_value=5, width="small"),
                "start_date": st.column_config.DateColumn("Start", format="DD.MM.YYYY"),
                "deadline": st.column_config.DateColumn("Deadline", format="DD.MM.YYYY"),
                "status": st.column_config.SelectboxColumn(
                    "Status", options=STATUSES, required=True, width="medium"
                ),
                "duration_minutes": st.column_config.NumberColumn("Min.", min_value=1, width="small"),
                "cognitive_load": st.column_config.SelectboxColumn(
                    "Kognitiv", options=COGNITIVE_LEVELS, width="small"
                ),
                "recurrence": st.column_config.TextColumn("Wiederholung", width="medium"),
                "hint": st.column_config.TextColumn("Hinweis", width="medium"),
                "micro_action": st.column_config.TextColumn("Nächster Schritt", width="large"),
                "waiting_for": st.column_config.TextColumn("Warte auf", width="medium"),
            },
            key="task_overview_editor",
        )

        originals = filtered.set_index("id")
        updates = []
        for row in edited.itertuples(index=False):
            original = originals.loc[row.id]
            new_duration = int(row.duration_minutes) if pd.notna(row.duration_minutes) else None
            old_duration = int(original["duration_minutes"]) if pd.notna(original["duration_minutes"]) else None
            new_cognitive = row.cognitive_load if pd.notna(row.cognitive_load) else None
            old_cognitive = original["cognitive_load"] if pd.notna(original["cognitive_load"]) else None
            new_priority = int(row.priority) if pd.notna(row.priority) else 3
            old_priority = int(original["priority"]) if pd.notna(original["priority"]) else 3
            if (
                row.status != original["status"]
                or new_priority != old_priority
                or new_duration != old_duration
                or new_cognitive != old_cognitive
            ):
                updates.append(
                    {
                        "status": row.status,
                        "old_status": original["status"],
                        "priority": new_priority,
                        "duration": new_duration,
                        "cognitive": new_cognitive,
                        "id": int(row.id),
                    }
                )
        if updates:
            recurring_count = 0
            with db_connection() as connection:
                for update in updates:
                    connection.execute(
                        """
                        UPDATE tasks SET priority=?, duration_minutes=?, cognitive_load=?
                        WHERE id=?
                        """,
                        (
                            update["priority"], update["duration"], update["cognitive"],
                            update["id"],
                        ),
                    )
                    if update["status"] == "Done" and update["old_status"] != "Done":
                        result = complete_task(connection, update["id"])
                        if result["created_id"] is not None:
                            recurring_count += 1
                    else:
                        connection.execute(
                            "UPDATE tasks SET status=? WHERE id=?",
                            (update["status"], update["id"]),
                        )
                        if update["status"] != "Done":
                            connection.execute(
                                "UPDATE tasks SET completed_at=NULL WHERE id=?",
                                (update["id"],),
                            )
            message = "Änderungen gespeichert"
            if recurring_count:
                message += f" · {recurring_count} Folgeaufgabe(n) angelegt"
            st.toast(message, icon="✅")

        st.divider()
        edit_rows = tasks.to_dict("records")
        edit_by_label = {task_label(row): int(row["id"]) for row in edit_rows}
        edit_cols = st.columns([4, 1])
        with edit_cols[0]:
            selected_edit_label = st.selectbox(
                "Task für Details auswählen", edit_by_label, key="edit_task_selector"
            )
        with edit_cols[1]:
            st.write("")
            if st.button("Details öffnen", type="primary", width="stretch"):
                edit_task_dialog(edit_by_label[selected_edit_label])
