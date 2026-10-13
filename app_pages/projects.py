"""Projektverwaltung von FocusFilter."""

from app_shared import *  # noqa: F403

st.caption("Neue Projekte stehen sofort in Filtern und Formularen zur Verfügung.")

with st.form("add_project", clear_on_submit=True):
    new_project_name = st.text_input("Neues Projekt")
    if st.form_submit_button("Projekt hinzufügen", type="primary"):
        clean_name = new_project_name.strip()
        if not clean_name:
            st.error("Bitte gib einen Projektnamen ein.")
        else:
            try:
                with db_connection() as connection:
                    connection.execute("INSERT INTO projects (name) VALUES (?)", (clean_name,))
                st.success(f"Projekt „{clean_name}“ hinzugefügt.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Dieses Projekt gibt es bereits.")

all_projects = read_projects(active_only=False)
if not all_projects.empty:
    st.dataframe(
        all_projects.rename(columns={"name": "Projekt", "active": "Aktiv"}),
        hide_index=True,
        width="stretch",
        column_config={"id": None, "Aktiv": st.column_config.CheckboxColumn("Aktiv")},
    )

    manage_cols = st.columns(2)
    choices = all_projects["name"].tolist()
    with manage_cols[0]:
        with st.form("rename_project"):
            old_name = st.selectbox("Projekt umbenennen", choices)
            renamed = st.text_input("Neuer Name")
            if st.form_submit_button("Umbenennen"):
                clean_name = renamed.strip()
                if not clean_name:
                    st.error("Bitte gib einen neuen Namen ein.")
                else:
                    try:
                        with db_connection() as connection:
                            connection.execute("UPDATE projects SET name = ? WHERE name = ?", (clean_name, old_name))
                            connection.execute("UPDATE tasks SET project = ? WHERE project = ?", (clean_name, old_name))
                        st.success("Projekt und zugehörige Tasks wurden aktualisiert.")
                        st.rerun()
                    except sqlite3.IntegrityError:
                        st.error("Dieser Projektname ist bereits vergeben.")
    with manage_cols[1]:
        with st.form("toggle_project"):
            toggle_name = st.selectbox("Projekt aktivieren/deaktivieren", choices)
            active_row = all_projects.loc[all_projects["name"] == toggle_name, "active"].iloc[0]
            target_active = not bool(active_row)
            action = "Aktivieren" if target_active else "Deaktivieren"
            st.caption("Deaktivieren blendet das Projekt in neuen Formularen aus. Bestehende Tasks bleiben erhalten.")
            if st.form_submit_button(action):
                with db_connection() as connection:
                    connection.execute(
                        "UPDATE projects SET active = ? WHERE name = ?", (int(target_active), toggle_name)
                    )
                state = "aktiviert" if target_active else "deaktiviert"
                st.success(f"Projekt wurde {state}.")
                st.rerun()
