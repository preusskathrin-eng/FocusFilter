"""Wochenreview von FocusFilter."""

from app_shared import *  # noqa: F403

if "review_saved_message" in st.session_state:
    st.success(st.session_state.pop("review_saved_message"))

review_header = st.columns([1, 1.2, 1.5])
with review_header[0]:
    review_date = st.date_input("Woche auswählen", value=date.today(), key="review_week")
week_start = monday_of(review_date)
week_end = week_start + timedelta(days=6)
with review_header[1]:
    st.write("")
    st.info(f"{week_start.strftime('%d.%m.%Y')} – {week_end.strftime('%d.%m.%Y')}")
with review_header[2]:
    review_project_filter = st.multiselect(
        "Projekt", project_names(active_only=False), placeholder="Alle Projekte",
        key="review_projects",
    )

review_tasks = read_tasks()
review_tasks = review_tasks[review_tasks["archived"].fillna(0).eq(0)].copy()
if review_project_filter:
    review_tasks = review_tasks[review_tasks["project"].isin(review_project_filter)]

saved_reviews = read_weekly_reviews(week_start)
saved_lookup = (
    saved_reviews.set_index("task_id")[["outcome", "note"]]
    if not saved_reviews.empty else pd.DataFrame(columns=["outcome", "note"])
)
review_tasks["review_result"] = review_tasks["id"].map(
    saved_lookup["outcome"] if "outcome" in saved_lookup else {}
).fillna("Nicht bewertet")
review_tasks["review_note"] = review_tasks["id"].map(
    saved_lookup["note"] if "note" in saved_lookup else {}
).fillna("")

review_metrics = st.columns(3)
review_metrics[0].metric(
    "Fortschritt gemacht", int((review_tasks["review_result"] == "Fortschritt gemacht").sum())
)
review_metrics[1].metric(
    "Erledigt", int((review_tasks["review_result"] == "Erledigt").sum())
)
review_metrics[2].metric(
    "Noch nicht bewertet", int((review_tasks["review_result"] == "Nicht bewertet").sum())
)

st.caption(
    "„Fortschritt gemacht“ dokumentiert die Woche, ohne den Task zu schließen. "
    "„Erledigt“ setzt zusätzlich seinen Status auf Done."
)
if review_tasks.empty:
    st.info("Für diese Auswahl gibt es keine Tasks.")
else:
    review_columns = ["id", "title", "project", "status", "review_result", "review_note"]
    reviewed = st.data_editor(
        review_tasks[review_columns],
        hide_index=True,
        width="stretch",
        disabled=["id", "title", "project", "status"],
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "title": st.column_config.TextColumn("Task", width="large"),
            "project": st.column_config.TextColumn("Projekt"),
            "status": st.column_config.TextColumn("Taskstatus", width="small"),
            "review_result": st.column_config.SelectboxColumn(
                "Wochenstatus", options=REVIEW_RESULTS, required=True, width="medium"
            ),
            "review_note": st.column_config.TextColumn("Review-Notiz", width="large"),
        },
        key=f"weekly_review_editor_{week_start.isoformat()}",
    )

    if st.button("Wochenreview speichern", type="primary"):
        saved_count = 0
        done_count = 0
        recurring_count = 0
        with db_connection() as connection:
            for row in reviewed.itertuples(index=False):
                if row.review_result == "Nicht bewertet":
                    connection.execute(
                        "DELETE FROM weekly_reviews WHERE week_start=? AND task_id=?",
                        (week_start.isoformat(), int(row.id)),
                    )
                    continue
                connection.execute(
                    """
                    INSERT INTO weekly_reviews (week_start, task_id, outcome, note, reviewed_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT (week_start, task_id) DO UPDATE SET
                        outcome=excluded.outcome,
                        note=excluded.note,
                        reviewed_at=CURRENT_TIMESTAMP
                    """,
                    (
                        week_start.isoformat(), int(row.id), row.review_result,
                        str(row.review_note or "").strip(),
                    ),
                )
                saved_count += 1
                if row.review_result == "Erledigt":
                    result = complete_task(connection, int(row.id))
                    if result["created_id"] is not None:
                        recurring_count += 1
                    done_count += 1
        st.session_state["review_saved_message"] = (
            f"{saved_count} Review-Einträge gespeichert; {done_count} Task(s) als erledigt "
            f"markiert; {recurring_count} Folgeaufgabe(n) vorhanden."
        )
        st.rerun()

history = read_weekly_reviews()
if not history.empty:
    with st.expander("Bisherige Wochen im Überblick"):
        history_summary = (
            history.groupby(["week_start", "outcome"]).size().unstack(fill_value=0).reset_index()
        )
        history_summary["week_start"] = pd.to_datetime(
            history_summary["week_start"], errors="coerce"
        ).dt.strftime("%d.%m.%Y")
        st.dataframe(history_summary, hide_index=True, width="stretch")
