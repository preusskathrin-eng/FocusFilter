"""CSV-Import für neue Tasks und ID-basierte Aktualisierungen."""

from app_shared import *  # noqa: F403


if "csv_import_result" in st.session_state:
    st.success(st.session_state.pop("csv_import_result"))

st.write(
    "CSV-Dateien können neue Tasks anlegen oder vorhandene Tasks über ihre ID aktualisieren. "
    "Vor dem Schreiben zeigt die App immer eine validierte Vorschau."
)
st.info(
    "Zeilen mit ID aktualisieren genau diesen Task. Dabei werden nur Spalten berücksichtigt, "
    "die in der Datei vorhanden sind. Ein mitgelieferter Titel muss zur ID passen. Leere "
    "Text- und Datumsfelder löschen den bisherigen Inhalt; ein Feld „Kommentar“ wird an die "
    "Notizen angehängt. Zeilen ohne ID werden als neue Tasks angelegt."
)

new_template = pd.DataFrame(
    [
        {
            "Titel": "Beispielaufgabe",
            "Projekt": "Sonstiges",
            "Kategorie": "Sonstiges",
            "Priorität": 3,
            "Startdatum": date.today().isoformat(),
            "Deadline": "",
            "Dauer_Minuten": 30,
            "Kognitive_Belastung": "Niedrig",
            "Status": "To Do",
            "Nächster_Schritt": "Ersten konkreten Schritt notieren",
            "Warte_auf": "",
            "Abhängigkeiten": "",
            "Notizen": "",
        }
    ]
)
update_template = pd.DataFrame(
    [
        {
            "ID": 1,
            "Titel": "Titel dient als Sicherheitsabgleich",
            "Neuer_Status": "In Progress",
            "Neue_Priorität": 2,
            "Neue_Deadline": "",
            "Neuer_Nächster_Schritt": "Nächsten Schritt ausführen",
            "Neues_Warte_auf": "",
            "Kommentar": "Kurze Ergänzung für die Notizen",
        }
    ]
)
with st.container(horizontal=True):
    st.download_button(
        "Vorlage für neue Tasks",
        data=new_template.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="task_import_neu.csv",
        mime="text/csv",
        icon=":material/download:",
    )
    st.download_button(
        "Vorlage für ID-Updates",
        data=update_template.to_csv(index=False, sep=";").encode("utf-8-sig"),
        file_name="task_updates_mit_id.csv",
        mime="text/csv",
        icon=":material/download:",
    )

st.caption(
    "Neue Tasks benötigen einen Titel. Fehlende Kategorie, Priorität, Status und CoRE-Fokus "
    "erhalten sichere Standardwerte. Neue Projektnamen werden automatisch angelegt."
)

uploaded_csv = st.file_uploader("CSV-Datei auswählen", type=["csv"])
if uploaded_csv is not None:
    try:
        raw_import = read_csv_bytes(uploaded_csv.getvalue())
        import_data = normalize_import_data(raw_import)
        import_data = classify_import_data(import_data, read_tasks())
    except (ValueError, pd.errors.EmptyDataError) as error:
        st.error(str(error))
    else:
        error_count = int(import_data["errors"].ne("").sum()) if not import_data.empty else 0
        update_count = int(import_data["action"].eq("Aktualisieren").sum()) if not import_data.empty else 0
        new_count = int(import_data["action"].eq("Neu").sum()) if not import_data.empty else 0

        summary = st.columns(3)
        summary[0].metric("Aktualisierungen", update_count)
        summary[1].metric("Neue Tasks", new_count)
        summary[2].metric("Fehler", error_count)

        preview_columns = [
            "source_row", "action", "id", "title", "project", "priority",
            "deadline", "status", "micro_action", "waiting_for", "comment", "errors",
        ]
        st.dataframe(
            import_data[preview_columns],
            hide_index=True,
            width="stretch",
            column_config={
                "source_row": "CSV-Zeile",
                "action": "Aktion",
                "id": st.column_config.NumberColumn("ID", format="%d", pinned=True),
                "title": st.column_config.TextColumn("Titel", pinned=True),
                "project": "Projekt",
                "priority": "Prio",
                "deadline": "Deadline",
                "status": "Status",
                "micro_action": "Nächster Schritt",
                "waiting_for": "Warte auf",
                "comment": "Kommentar",
                "errors": "Fehler",
            },
        )

        if error_count:
            st.error(
                f"{error_count} Zeile(n) enthalten Fehler. Es wird nichts geschrieben, "
                "bis alle Fehler korrigiert sind."
            )
        elif import_data.empty:
            st.warning("Die CSV enthält keine Datenzeilen.")
        else:
            skip_duplicates = st.checkbox(
                "Neue Tasks mit bereits vorhandener Kombination aus Titel und Projekt überspringen",
                value=True,
                disabled=new_count == 0,
            )
            if st.button(
                "Geprüfte Änderungen übernehmen",
                type="primary",
                icon=":material/save:",
            ):
                backup_path = create_timestamped_backup()
                with db_connection() as connection:
                    result = apply_task_import(
                        connection,
                        import_data,
                        skip_duplicates=skip_duplicates,
                    )
                st.session_state["csv_import_result"] = (
                    f"{result['updated']} aktualisiert, {result['inserted']} neu angelegt, "
                    f"{result['skipped']} übersprungen. Sicherung: {backup_path.name}"
                )
                st.rerun()
