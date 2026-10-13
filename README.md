# FocusFilter

![FocusFilter-Logo](images/logo.png)

FocusFilter ist eine lokale Aufgabenplanung mit Streamlit und SQLite. Die App hilft dabei,
Aufgaben nicht nur nach Projekt und Termin, sondern auch nach verfügbarer Zeit, kognitiver
Belastung und aktueller Machbarkeit auszuwählen.

## Funktionen

- fokussierte Heute-Ansicht mit Zeit-, Belastungs- und Kategorie filtern
- editierbare Übersicht mit Suche, Sortierung und Projektfiltern
- wiederkehrende Aufgaben mit festem Rhythmus oder Abstand ab Erledigung
- Wochenreview mit **Fortschritt gemacht** und **Erledigt**
- Statistik und eingrenzbare Timeline
- CSV-Export sowie validierter Import für neue und vorhandene Tasks
- frei verwaltbare Projekte statt fest codierter Projektlisten
- lokale SQLite-Datenbank und tägliche Sicherung

## Schnellstart unter Windows

Vorausgesetzt wird Python 3.11 oder neuer.

1. Repository herunterladen oder klonen.
2. Optional die Demo-Datenbank aktivieren:

   ```powershell
   Copy-Item .\examples\tasks.example.db .\tasks.db
   ```

3. `FocusFilter starten.vbs` doppelklicken. Der Starter installiert bei Bedarf die Pakete
   aus `requirements.txt` und öffnet die App unter `http://127.0.0.1:8507`.

Für sichtbare Diagnosemeldungen kann stattdessen `FocusFilter starten.cmd` verwendet werden.
Ohne kopierte Demo-Datenbank erzeugt FocusFilter beim ersten Start automatisch eine leere
`tasks.db`.

## Manuelle Installation

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run streamlit_app.py
```

## Beispieldatenbank

`examples/tasks.example.db` enthält wenige generische Beispieldatensätze, darunter eine
wiederkehrende Haushaltsaufgabe, eine wartende Aufgabe und abgeschlossene Arbeit für das
Wochenreview. Es sind keine Daten aus der ursprünglichen Arbeitsdatenbank enthalten.

Die Beispieldatenbank lässt sich reproduzierbar neu erzeugen:

```powershell
python scripts/create_example_db.py --force
```

## CSV-Import

Die Seite **CSV-Import** stellt Vorlagen für neue Tasks und ID-basierte Aktualisierungen
bereit. Vor jeder Änderung zeigt FocusFilter eine validierte Vorschau. Updates prüfen die
Kombination aus ID und Titel; Sammeländerungen werden transaktional geschrieben und vorher
gesichert.

## Tests

```powershell
python -m unittest discover -s tests -v
```

Unter Windows kann alternativ `Tests ausführen.cmd` doppelt angeklickt werden. Die
Navigationstests arbeiten mit einer temporären Kopie der Demo-Datenbank und verändern sie
nicht.

## Projektstruktur

```text
streamlit_app.py        zentraler Einstieg und Seitennavigation
app_shared.py           gemeinsame UI- und Datenbankfunktionen
app_pages/              einzelne Ansichten
utils/                  testbare Fachlogik
scripts/                Import-, Migrations- und Demo-Werkzeuge
examples/               kleine Beispieldatenbank
tests/                  Logik- und Streamlit-Tests
images/                 FocusFilter-Logo
```

## Daten und Datenschutz

Alle Aufgaben liegen lokal in `tasks.db`. Diese Datei, Sicherungen und lokale Secrets werden
durch `.gitignore` ausgeschlossen. Vor einem Commit sollte trotzdem mit `git status` geprüft
werden, dass keine persönlichen Exporte oder Datenbanken aufgenommen werden.
