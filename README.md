# Jobs

Arbeitsmarkt-Monitoring Rems-Murr / Ostalb. `collect_jobs.py` läuft täglich
(`.github/workflows/collect.yml`, 08:17 UTC) und schreibt `data/` sowie
`arbeitsmarkt_auswertung.xlsx`.

## Quellen

- **BA-Jobsuche**: `data/jobs_log.csv`, `berufe.csv`, `snapshots.csv`.
- **Karriereseiten regionaler Arbeitgeber**: aus dem Repo
  [ScrapJobs](https://github.com/Penetrationpasi-hub/ScrapJobs) (`stellen.json`)
  → `data/scrapjobs_log.csv` (`first_seen`/`last_seen` aus ScrapJobs selbst,
  `aktiv` = steht in der aktuellen `stellen.json`) und `data/scrapjobs_stand.json`.
  Ist `stellen.json` älter als 2 Tage, erscheint im Actions-Log eine Warnung.

## Gemeinsame Auswertung: `data/stellen_alle.csv`

Wird bei jedem Lauf komplett neu aus beiden Logs gebaut. Jede Stelle steht
genau einmal darin.

| Spalte | Inhalt |
|---|---|
| `stellen_id` | `BA:<refnr>` oder `SJ:<id>` |
| `herkunft` | `BA`, `Karriereseite` oder `beide` |
| `ba_refnr`, `scrapjobs_id` | Schlüssel in den Quell-Logs |
| `titel`, `arbeitgeber`, `ort` | wie in der Quelle (bei `beide`: BA) |
| `kreis` | Landkreis aus dem Arbeitsort (`orte.py`), überschneidungsfrei |
| `ba_suchgebiet` | BA-Suchgebiet (Umkreissuche), nur BA-Stellen |
| `beruf`, `beruf_quelle` | BA-Beruf; für Karriereseiten über gleichen Titel in den BA-Daten (`Titel-Abgleich`), sonst leer (`offen`) |
| `branche`, `branche_quelle` | BA-Berufssegment (siehe „Branchen“ unten) aus dem Beruf, sonst aus Stichwörtern im Titel, sonst übliche Berufshauptgruppe des Arbeitgebers in den BA-Daten |
| `hauptgruppe` | KldB-2010-Berufshauptgruppe (2-Steller), aus der `branche` abgeleitet wird |
| `url` | Link zur Karriereseite (nur bei Karriereseiten-Stellen) |
| `first_seen`, `last_seen`, `standzeit_tage` | bei `beide` der gemeinsame Zeitraum |
| `offen` | `ja`, wenn am BA-Stichtag gesehen oder in der aktuellen `stellen.json` |

**Doppelte** (gleiche Stelle bei der BA und auf der Karriereseite): gleicher
Arbeitgeber (ohne Rechtsform, ein Name im anderen enthalten), gleicher Titel
(ohne m/w/d), Zeiträume höchstens 14 Tage auseinander. Jede BA-Stelle wird
höchstens einer Karriereseiten-Stelle zugeordnet.

**Kreise**: neue Gemeinden in `orte.py` (`KREISE`) ergänzen; nicht erkannte
Orte landen in „andere Region“.

In der Excel: Blätter **Gesamt-Übersicht** (offene Stellen je Kreis, Branche,
Arbeitgeber nach Herkunft) und **Alle Stellen** (alle offenen Stellen, mit
Filter). Die übrigen BA-Blätter bleiben reine BA-Zahlen.

## Branchen (Blatt „Branchen“)

Einteilung nach der offiziellen **Klassifikation der Berufe 2010 (KldB 2010)**
der Bundesagentur für Arbeit, zusammengefasst wie in der BA-Statistik
(Methodenbericht „Berufssektoren und Berufssegmente“):

| Segment | Berufshauptgruppen |
|---|---|
| S11 Land-, Forst- und Gartenbauberufe | 11, 12 |
| S12 Fertigungsberufe | 21, 22, 23, 24, 28, 93 |
| S13 Fertigungstechnische Berufe | 25, 26, 27 |
| S14 Bau- und Ausbauberufe | 31, 32, 33, 34 |
| S21 Lebensmittel- und Gastgewerbeberufe | 29, 63 |
| S22 Medizinische u. nicht-medizinische Gesundheitsberufe | 81, 82 |
| S23 Soziale und kulturelle Dienstleistungsberufe | 83, 84, 91, 94 |
| S31 Handelsberufe | 61, 62 |
| S32 Berufe in Unternehmensführung und -organisation | 71 |
| S33 Unternehmensbezogene Dienstleistungsberufe | 72, 73, 92 |
| S41 IT- und naturwissenschaftliche Dienstleistungsberufe | 41, 42, 43 |
| S51 Sicherheitsberufe | 01, 53 |
| S52 Verkehrs- und Logistikberufe | 51, 52 |
| S53 Reinigungsberufe | 54 |

Dieselben Segmentnamen wie in `data_historie/ba_berufe.csv`, daher stehen
im Blatt Stellen und Arbeitslose je Segment nebeneinander (Engpass-Kennzahl
„Arbeitslose je gemeldeter Stelle“, Agentur Waiblingen).

Woher der KldB-Code eines Berufs kommt (Blatt „Branchen-Zuordnung“, Spalte
„Zuordnung über“):

1. **Hand**: `data/beruf_kldb_manuell.csv` (Spalten `beruf,kldb`, z. B.
   `Industriemechaniker/in,25102`) – Korrekturen, haben Vorrang.
2. **KldB**: `data/beruf_kldb.csv`, automatisch über die BERUFENET-API
   (`tools/kldb_zuordnung.py`, läuft im Datenlauf vor der Auswertung, je
   Lauf höchstens `KLDB_MAX` = 400 neue Berufe, häufigste zuerst).
3. **Stichwort**: Rückfall in `branchen.py` (`REGELN`, Schlüsselwörter →
   Berufshauptgruppe), solange ein Beruf noch nicht nachgeschlagen ist, und
   für freie Titel der Karriereseiten.
4. **offen**: keine Zuordnung → „Keine Angabe“.

Alles wird bei jedem Lauf aus den Rohdaten neu gerechnet; Korrekturen wirken
rückwirkend. Diagnose der BERUFENET-Antworten: Workflow „Daten sammeln“ von
Hand starten mit Haken bei `kldb_probe`.

## Tests

```bash
python -m pytest -q
```
