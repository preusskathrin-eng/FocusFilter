"""Haupteinstieg für FocusFilter."""

from pathlib import Path

import streamlit as st

from app_shared import create_daily_backup, init_db


LOGO_PATH = Path(__file__).resolve().parent / "images" / "logo.png"

st.set_page_config(
    page_title="FocusFilter",
    page_icon=str(LOGO_PATH),
    layout="wide",
)

create_daily_backup()
init_db()

page = st.navigation(
    {
        "Planen": [
            st.Page("app_pages/today.py", title="Heute", icon=":material/today:", default=True),
            st.Page("app_pages/overview.py", title="Übersicht", icon=":material/checklist:"),
            st.Page("app_pages/new_task.py", title="Neuer Task", icon=":material/add_task:"),
        ],
        "Reflektieren": [
            st.Page(
                "app_pages/weekly_review.py",
                title="Wochenreview",
                icon=":material/calendar_month:",
            ),
            st.Page("app_pages/statistics.py", title="Statistik", icon=":material/analytics:"),
            st.Page("app_pages/timeline.py", title="Timeline", icon=":material/timeline:"),
        ],
        "Verwalten": [
            st.Page("app_pages/csv_import.py", title="CSV-Import", icon=":material/upload_file:"),
            st.Page("app_pages/projects.py", title="Projekte", icon=":material/folder:"),
        ],
    },
    position="sidebar",
)

logo_column, title_column = st.columns([1, 7], vertical_alignment="center")
with logo_column:
    st.image(str(LOGO_PATH), width="stretch")
with title_column:
    st.title(page.title, icon=page.icon)
    st.caption("Aufgaben planen, den nächsten Schritt sehen und Fortschritt direkt festhalten.")

page.run()

st.divider()
st.caption("FocusFilter v1.0 · Lokale Datenbank: tasks.db · tägliche Sicherung aktiv")
