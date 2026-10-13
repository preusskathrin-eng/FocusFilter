"""Heute-Seite von FocusFilter."""

from app_shared import *  # noqa: F403

all_tasks = read_tasks()
active_tasks = all_tasks[all_tasks["archived"].fillna(0).eq(0)].copy()
all_statuses = all_tasks.set_index("id")["status"].to_dict()
available = active_tasks.loc[available_now_mask(active_tasks, all_statuses)].copy()
deadlines = pd.to_datetime(active_tasks["deadline"], errors="coerce")
overdue = active_tasks[
    deadlines.notna()
    & deadlines.lt(pd.Timestamp(date.today()))
    & active_tasks["status"].ne("Done")
]
waiting = active_tasks[active_tasks["waiting_for"].fillna("").str.strip().ne("")]

today_metrics = st.columns(4)
today_metrics[0].metric("Jetzt machbar", len(available))
today_metrics[1].metric("Überfällig", len(overdue))
today_metrics[2].metric("Wartet", len(waiting))
today_metrics[3].metric("Aktive Tasks", len(active_tasks))

with st.expander("⚡ Aufgabe schnell erfassen", expanded=False):
    with st.form("quick_capture", clear_on_submit=True):
        quick_cols = st.columns([2.5, 1.2, 1])
        with quick_cols[0]:
            quick_title = st.text_input("Was muss erledigt werden?")
        with quick_cols[1]:
            quick_projects = [NO_PROJECT] + project_names()
            quick_project = st.selectbox("Projekt", quick_projects)
        with quick_cols[2]:
            quick_priority = st.selectbox("Priorität", [3, 2, 1, 4, 5])
        if st.form_submit_button("Aufgabe erfassen", type="primary"):
            if not quick_title.strip():
                st.error("Bitte gib einen Titel ein.")
            else:
                with db_connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO tasks (title, project, category, core_focus, priority, status)
                        VALUES (?, ?, 'Sonstiges', 'Keiner', ?, 'To Do')
                        """,
                        (
                            quick_title.strip(),
                            None if quick_project == NO_PROJECT else quick_project,
                            quick_priority,
                        ),
                    )
                st.rerun()

st.subheader("Was passt gerade?")
focus_cols = st.columns(3)
with focus_cols[0]:
    focus_minutes = st.number_input(
        "Höchstens Minuten", min_value=1, value=None, step=5, key="today_minutes"
    )
with focus_cols[1]:
    focus_load = st.multiselect(
        "Kognitive Belastung",
        COGNITIVE_LEVELS + ["Nicht eingestuft"],
        default=[],
        placeholder="Alle Belastungen",
        key="today_cognitive",
    )
with focus_cols[2]:
    focus_categories = st.multiselect(
        "Kategorie",
        sorted(available["category"].dropna().unique().tolist(), key=str.casefold),
        key="today_categories",
        placeholder="Alle Kategorien",
    )

if focus_minutes is not None:
    duration_values = pd.to_numeric(available["duration_minutes"], errors="coerce")
    available = available[duration_values.notna() & duration_values.le(int(focus_minutes))]
if focus_load:
    load_values = available["cognitive_load"].fillna("").replace("", "Nicht eingestuft")
    available = available[load_values.isin(focus_load)]
if focus_categories:
    available = available[available["category"].isin(focus_categories)]
available = available.sort_values(["priority", "deadline", "duration_minutes"], na_position="last")

if available.empty:
    st.info("Für diese Auswahl gibt es gerade keine machbare Aufgabe.")
else:
    st.caption(f"{len(available)} passende Aufgabe(n) · die ersten zehn werden angezeigt")
    for task in available.head(10).to_dict("records"):
        with st.container(border=True):
            content, start_col, done_col, later_col, edit_col = st.columns([5, 1, 1, 1, 1])
            with content:
                duration_text = f"{int(task['duration_minutes'])} Min." if pd.notna(task["duration_minutes"]) else "Dauer offen"
                load_text = task["cognitive_load"] or "nicht eingestuft"
                st.markdown(f"**#{task['id']} · {task['title']}**")
                st.caption(
                    f"{task['project'] or NO_PROJECT} · Prio {task['priority'] or 3} · "
                    f"{duration_text} · kognitiv {load_text.lower()}"
                )
                if recurrence_label(task):
                    st.caption(f":material/repeat: {recurrence_label(task)}")
                if task["micro_action"]:
                    st.write(task["micro_action"])
            if start_col.button("Start", key=f"today_start_{task['id']}", width="stretch"):
                with db_connection() as connection:
                    connection.execute(
                        "UPDATE tasks SET status='In Progress', deferred_until=NULL WHERE id=?",
                        (task["id"],),
                    )
                st.rerun()
            if done_col.button("Fertig", key=f"today_done_{task['id']}", width="stretch"):
                with db_connection() as connection:
                    result = complete_task(connection, int(task["id"]))
                if result["created_id"] is not None:
                    st.toast(
                        f"Folgeaufgabe #{result['created_id']} wurde angelegt.",
                        icon=":material/repeat:",
                    )
                st.rerun()
            if later_col.button("Morgen", key=f"today_later_{task['id']}", width="stretch"):
                with db_connection() as connection:
                    connection.execute(
                        "UPDATE tasks SET deferred_until=? WHERE id=?",
                        ((date.today() + timedelta(days=1)).isoformat(), task["id"]),
                    )
                st.rerun()
            if edit_col.button("Details", key=f"today_edit_{task['id']}", width="stretch"):
                edit_task_dialog(int(task["id"]))
