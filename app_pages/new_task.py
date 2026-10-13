"""Neue-Task-Seite von FocusFilter."""

from app_shared import *  # noqa: F403


NEW_TASK_WIDGET_KEYS = (
    "new_task_title",
    "new_task_project",
    "new_task_category",
    "new_task_core_focus",
    "new_task_priority",
    "new_task_start_date",
    "new_task_deadline",
    "new_task_duration",
    "new_task_duration_minutes",
    "new_task_cognitive_load",
    "new_task_micro_action",
    "new_task_waiting_for",
    "new_task_dependencies",
    "new_task_notes",
    "new_task_recurrence_preset",
    "new_task_recurrence_interval",
    "new_task_recurrence_unit",
    "new_task_recurrence_anchor",
    "new_task_embodiment_flag",
)

if st.session_state.pop("new_task_reset_requested", False):
    for widget_key in NEW_TASK_WIDGET_KEYS:
        st.session_state.pop(widget_key, None)
    st.session_state["new_task_saved_message"] = "Task gespeichert."

if saved_message := st.session_state.pop("new_task_saved_message", None):
    st.success(saved_message)

projects = project_names()
if not projects:
    st.warning("Lege zuerst auf der Seite „Projekte“ mindestens ein Projekt an.")
else:
    st.caption("* Pflichtfeld · Bei einem Fehler bleiben alle Eingaben erhalten.")
    with st.form("new_task", clear_on_submit=False):
        title = st.text_input("Titel *", key="new_task_title")
        project = st.selectbox(
            "Projekt/Subprojekt *", projects, key="new_task_project"
        )
        category = st.selectbox(
            "Hauptkategorie *", CATEGORIES, key="new_task_category"
        )
        core_focus = st.selectbox(
            "CoRE-Fokus", CORE_OPTIONS, key="new_task_core_focus"
        )
        priority = st.slider(
            "Priorität (1 = kritisch)", 1, 5, 3, key="new_task_priority"
        )

        date_cols = st.columns(2)
        with date_cols[0]:
            start_date = st.date_input(
                "Startdatum", value=date.today(), key="new_task_start_date"
            )
        with date_cols[1]:
            deadline = st.date_input(
                "Deadline",
                value=None,
                key="new_task_deadline",
                help="Pflichtfeld, sobald eine Wiederholung ausgewählt ist.",
            )

        duration = st.text_input(
            "Geschätzte Dauer (z. B. 4h oder 2 Tage)", key="new_task_duration"
        )
        duration_minutes = st.number_input(
            "Dauer in Minuten (für Aufwandfilter)",
            min_value=1,
            value=None,
            step=5,
            key="new_task_duration_minutes",
        )
        cognitive_load = st.selectbox(
            "Kognitive Belastung",
            ["Nicht eingestuft"] + COGNITIVE_LEVELS,
            key="new_task_cognitive_load",
        )
        micro_action = st.text_area(
            "Nächster konkreter Schritt", key="new_task_micro_action"
        )
        waiting_for = st.text_input("Warte auf", key="new_task_waiting_for")
        dependency_tasks = read_tasks()
        dependency_choices = {
            task_label(row): int(row["id"]) for row in dependency_tasks.to_dict("records")
        }
        dependencies = st.multiselect(
            "Abhängigkeiten",
            dependency_choices,
            key="new_task_dependencies",
            help="Die neue Aufgabe wird erst machbar, wenn alle ausgewählten Tasks erledigt sind.",
        )
        notes = st.text_area(
            "Notizen / Trigger / Sonstiges", key="new_task_notes"
        )
        st.subheader("Wiederholung")
        recurrence_interval, recurrence_unit, recurrence_anchor = recurrence_form_controls(
            "new_task"
        )
        embodiment_flag = st.checkbox(
            "Braucht Embodiment-/Regulation-Check?",
            key="new_task_embodiment_flag",
        )

        if st.form_submit_button(
            "Task speichern", type="primary", key="new_task_submit"
        ):
            if not title.strip():
                st.error("Bitte fülle das Pflichtfeld „Titel“ aus.")
            else:
                try:
                    recurrence_values = recurrence_storage_values(
                        recurrence_interval,
                        recurrence_unit,
                        recurrence_anchor,
                        deadline,
                    )
                except ValueError as error:
                    st.error(str(error))
                else:
                    with db_connection() as connection:
                        connection.execute(
                            """
                            INSERT INTO tasks
                            (title, project, category, core_focus, priority, start_date, deadline,
                             duration, dependencies, micro_action, waiting_for, notes,
                             embodiment_flag, duration_minutes, cognitive_load,
                             recurrence_interval, recurrence_unit, recurrence_anchor,
                             recurrence_series_id, recurrence_day)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                title.strip(), project, category, core_focus, priority,
                                start_date.isoformat() if start_date else None,
                                deadline.isoformat() if deadline else None,
                                duration.strip(),
                                ",".join(
                                    str(dependency_choices[label]) for label in dependencies
                                ),
                                micro_action.strip(), waiting_for.strip(), notes.strip(),
                                int(embodiment_flag), duration_minutes,
                                None if cognitive_load == "Nicht eingestuft" else cognitive_load,
                                *recurrence_values,
                            ),
                        )
                    st.session_state["new_task_reset_requested"] = True
                    st.rerun()
