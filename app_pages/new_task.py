"""Neue-Task-Seite von FocusFilter."""

from app_shared import *  # noqa: F403

projects = project_names()
if not projects:
    st.warning("Lege zuerst auf der Seite „Projekte“ mindestens ein Projekt an.")
else:
    with st.form("new_task", clear_on_submit=True):
        title = st.text_input("Titel *")
        project = st.selectbox("Projekt/Subprojekt", projects)
        category = st.selectbox("Hauptkategorie", CATEGORIES)
        core_focus = st.selectbox("CoRE-Fokus", CORE_OPTIONS)
        priority = st.slider("Priorität (1 = kritisch)", 1, 5, 3)

        date_cols = st.columns(2)
        with date_cols[0]:
            start_date = st.date_input("Startdatum", value=date.today())
        with date_cols[1]:
            deadline = st.date_input("Deadline", value=None)

        duration = st.text_input("Geschätzte Dauer (z. B. 4h oder 2 Tage)")
        duration_minutes = st.number_input(
            "Dauer in Minuten (für Aufwandfilter)", min_value=1, value=None, step=5
        )
        cognitive_load = st.selectbox(
            "Kognitive Belastung", ["Nicht eingestuft"] + COGNITIVE_LEVELS
        )
        micro_action = st.text_area("Nächster konkreter Schritt")
        waiting_for = st.text_input("Warte auf")
        dependency_tasks = read_tasks()
        dependency_choices = {
            task_label(row): int(row["id"]) for row in dependency_tasks.to_dict("records")
        }
        dependencies = st.multiselect(
            "Abhängigkeiten", dependency_choices,
            help="Die neue Aufgabe wird erst machbar, wenn alle ausgewählten Tasks erledigt sind.",
        )
        notes = st.text_area("Notizen / Trigger / Sonstiges")
        st.subheader("Wiederholung")
        recurrence_interval, recurrence_unit, recurrence_anchor = recurrence_form_controls(
            "new_task"
        )
        embodiment_flag = st.checkbox("Braucht Embodiment-/Regulation-Check?")

        if st.form_submit_button("Task speichern", type="primary"):
            if not title.strip():
                st.error("Bitte gib einen Titel ein.")
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
                    st.success("Task gespeichert.")
