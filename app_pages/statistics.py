"""Statistik-Dashboard von FocusFilter."""

from app_shared import *  # noqa: F403


STATUS_COLORS = {
    "To Do": "#4C78A8",
    "In Progress": "#F2B134",
    "Warte": "#8F6BAE",
    "Done": "#43A047",
}
PRIORITY_COLORS = {
    "1": "#B42318",
    "2": "#E76F51",
    "3": "#E9C46A",
    "4": "#4CA3A3",
    "5": "#4C78A8",
}

all_stats = read_tasks()
all_stats = all_stats[all_stats["archived"].fillna(0).eq(0)].copy()
completed_count = int(all_stats["status"].eq("Done").sum())

include_done = st.toggle(
    "Erledigte Tasks einbeziehen",
    value=False,
    key="statistics_include_done",
    help="Standardmäßig zeigen die Diagramme nur Tasks, an denen noch gearbeitet wird.",
)
stats = all_stats if include_done else all_stats[all_stats["status"].ne("Done")].copy()

if include_done:
    st.caption(f"Auswertung von {len(stats)} nicht archivierten Tasks einschließlich erledigter Tasks.")
else:
    st.caption(
        f"Auswertung von {len(stats)} aktiven Tasks. {completed_count} erledigte Tasks sind ausgeblendet."
    )

if stats.empty:
    st.info("Für diese Auswahl sind keine Tasks vorhanden.")
else:
    chart_cols = st.columns(2)
    with chart_cols[0]:
        visible_statuses = STATUSES if include_done else [status for status in STATUSES if status != "Done"]
        status_counts = (
            stats["status"].value_counts().reindex(visible_statuses, fill_value=0).rename_axis("Status").reset_index(name="Anzahl")
        )
        status_figure = px.bar(
            status_counts,
            x="Status",
            y="Anzahl",
            color="Status",
            color_discrete_map=STATUS_COLORS,
            category_orders={"Status": visible_statuses},
            title="Tasks nach Status",
            text="Anzahl",
        )
        status_figure.update_layout(showlegend=False)
        status_figure.update_traces(textposition="outside", cliponaxis=False)
        st.plotly_chart(status_figure, width="stretch")

    with chart_cols[1]:
        project_counts = stats["project"].fillna(NO_PROJECT).value_counts()
        st.plotly_chart(
            px.pie(
                names=project_counts.index,
                values=project_counts.values,
                title="Tasks nach Projekt",
                hole=0.35,
            ),
            width="stretch",
        )

    priority_counts = (
        stats["priority"]
        .fillna(3)
        .astype(int)
        .value_counts()
        .reindex(range(1, 6), fill_value=0)
        .rename_axis("Priorität")
        .reset_index(name="Anzahl")
    )
    priority_counts["Priorität"] = priority_counts["Priorität"].astype(str)
    priority_figure = px.bar(
        priority_counts,
        x="Priorität",
        y="Anzahl",
        color="Priorität",
        color_discrete_map=PRIORITY_COLORS,
        category_orders={"Priorität": ["1", "2", "3", "4", "5"]},
        labels={"Priorität": "Priorität (1 = höchste)"},
        title="Prioritätsverteilung",
        text="Anzahl",
    )
    priority_figure.update_layout(showlegend=False)
    priority_figure.update_traces(textposition="outside", cliponaxis=False)
    st.plotly_chart(priority_figure, width="stretch")
