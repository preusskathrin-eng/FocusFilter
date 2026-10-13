"""Timeline-Seite von FocusFilter."""

from app_shared import *  # noqa: F403


period_mode = st.segmented_control(
    "Zeitraum",
    ["Ab heute", "Letzte 30 Tage", "Dieses Jahr", "Alles", "Benutzerdefiniert"],
    default="Ab heute",
    key="timeline_period_mode",
    wrap=True,
)

today = date.today()
filter_start = filter_end = None
if period_mode == "Ab heute":
    filter_start = today
elif period_mode == "Letzte 30 Tage":
    filter_start = today - timedelta(days=29)
    filter_end = today
elif period_mode == "Dieses Jahr":
    filter_start = date(today.year, 1, 1)
    filter_end = date(today.year, 12, 31)
elif period_mode == "Benutzerdefiniert":
    date_columns = st.columns(2)
    with date_columns[0]:
        filter_start = st.date_input(
            "Von",
            value=today - timedelta(days=30),
            key="timeline_custom_start",
        )
    with date_columns[1]:
        filter_end = st.date_input(
            "Bis",
            value=today,
            key="timeline_custom_end",
        )
    if filter_start > filter_end:
        st.error("Das Von-Datum muss vor dem Bis-Datum liegen.")
        st.stop()

timeline = read_tasks()
timeline = timeline.loc[timeline_task_mask(timeline)].copy()
if timeline.empty:
    st.info("Keine offenen, nicht archivierten Tasks für die Timeline vorhanden.")
else:
    timeline["start"] = pd.to_datetime(timeline["start_date"], errors="coerce")
    timeline["end"] = pd.to_datetime(timeline["deadline"], errors="coerce")
    timeline = align_timeline_starts_with_dependencies(timeline)

    timeline = timeline[timeline["start"].notna() & timeline["end"].notna()]
    if timeline.empty:
        st.info("Keine Tasks mit Startdatum und Deadline vorhanden.")
    else:
        available_count = len(timeline)
        timeline = timeline.loc[
            timeline_overlap_mask(timeline, start=filter_start, end=filter_end)
        ].copy()
        if timeline.empty:
            st.info("Im gewählten Zeitraum liegen keine Tasks mit Startdatum und Deadline.")
            st.stop()

        if filter_start is None and filter_end is None:
            period_caption = "gesamter Zeitraum"
        elif filter_end is None:
            period_caption = f"ab {filter_start.strftime('%d.%m.%Y')}"
        else:
            period_caption = (
                f"{filter_start.strftime('%d.%m.%Y')} bis {filter_end.strftime('%d.%m.%Y')}"
            )
        st.caption(
            f"{len(timeline)} von {available_count} offenen planbaren Tasks · {period_caption}"
        )

        timeline = timeline.sort_values("start")
        figure = px.timeline(
            timeline,
            x_start="start", x_end="end", y="title", color="project",
            hover_data=["id", "status", "dependencies", "waiting_for", "micro_action"],
        )
        figure.update_yaxes(autorange="reversed")
        figure.update_layout(height=max(500, 32 * len(timeline)), title="Geplanter zeitlicher Verlauf")
        axis_start = (
            pd.Timestamp(filter_start)
            if filter_start is not None
            else timeline["start"].min()
        )
        axis_end = (
            pd.Timestamp(filter_end)
            if filter_end is not None
            else timeline["end"].max()
        )
        if axis_end <= axis_start:
            axis_end = axis_start + pd.Timedelta(days=1)
        visible_days = max((axis_end - axis_start).days, 1)
        if visible_days <= 120:
            tick_format = "%d.%m.%Y"
        elif visible_days <= 730:
            tick_format = "%m.%Y"
        else:
            tick_format = "%Y"
        figure.update_xaxes(
            range=[axis_start, axis_end],
            tickformat=tick_format,
            hoverformat="%d.%m.%Y",
        )
        st.plotly_chart(figure, width="stretch")
