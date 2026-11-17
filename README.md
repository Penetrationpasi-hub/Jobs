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
| `branche`, `branche_quelle` | aus dem Beruf (`branchen.py`), sonst aus Stichwörtern im Titel, sonst übliche Branche des Arbeitgebers in den BA-Daten |
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

## Tests

```bash
python -m pytest -q
```
