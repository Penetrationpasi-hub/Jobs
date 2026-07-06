#!/usr/bin/env python3
"""
BA-Jobmonitor: Sammelt taeglich Stellenangebote der Bundesagentur fuer Arbeit
fuer Waiblingen, Rems-Murr-Kreis und Ostalbkreis ueber die Jobsuche-API.

Auth: X-API-Key: jobboerse-jobsuche (oeffentliche clientId, keine Registrierung noetig)
API-Doku: https://github.com/bundesAPI/jobsuche-api

Outputs (im Ordner data/):
  snapshots.csv   - ein Datensatz pro Tag und Region (Gesamtzahlen, Verteilungen)
  berufe.csv      - Anzahl Stellen pro Beruf, Tag und Region (Top-Auswertung)
  jobs_log.csv    - jede jemals gesehene Stelle mit first_seen/last_seen
                    -> ermoeglicht Laufzeit- und Fluktuationsanalysen
"""

import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

API_BASE = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs"
HEADERS = {
    "X-API-Key": "jobboerse-jobsuche",
    "User-Agent": "ba-jobmonitor/1.0 (privates Arbeitsmarkt-Monitoring)",
}

# Regionen: Suche ueber Ort + Umkreis in km.
# Die API kennt keinen sauberen Landkreis-Filter, daher Naeherung ueber Umkreise.
# Waiblingen eng (15 km) als Kernregion, die Kreise grob ueber zentrale Orte.
REGIONS = {
    "waiblingen_15km": {"wo": "Waiblingen", "umkreis": 15},
    "rems-murr-kreis": {"wo": "Backnang", "umkreis": 25},
    "ostalbkreis": {"wo": "Aalen", "umkreis": 30},
}

PAGE_SIZE = 100
MAX_PAGES = 60          # Sicherheitslimit: 6000 Stellen pro Region
REQUEST_PAUSE = 1.0     # Sekunden zwischen Requests, hoeflich bleiben
DATA_DIR = Path(__file__).parent / "data"


def fetch_page(params: dict) -> dict:
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{API_BASE}?{qs}", headers=HEADERS)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"  Fehler (Versuch {attempt + 1}/3): {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Abruf fehlgeschlagen: {params}")


def fetch_region(region_params: dict) -> tuple[list[dict], int]:
    """Alle Stellen einer Region einsammeln (paginiert)."""
    jobs = []
    max_ergebnisse = 0
    for page in range(1, MAX_PAGES + 1):
        params = {
            "angebotsart": 1,        # 1 = Arbeit
            "page": page,
            "size": PAGE_SIZE,
            "pav": "false",          # keine privaten Arbeitsvermittler
            **region_params,
        }
        data = fetch_page(params)
        max_ergebnisse = int(data.get("maxErgebnisse", 0))
        batch = data.get("stellenangebote", [])
        if not batch:
            break
        jobs.extend(batch)
        if len(jobs) >= max_ergebnisse:
            break
        time.sleep(REQUEST_PAUSE)
    return jobs, max_ergebnisse


def append_csv(path: Path, fieldnames: list[str], rows: list[dict]):
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            w.writeheader()
        w.writerows(rows)


def update_jobs_log(path: Path, today: str, seen: dict[str, dict]):
    """Stellen-Log fortschreiben: neue Stellen anlegen, bekannte mit last_seen aktualisieren."""
    fieldnames = ["refnr", "region", "beruf", "titel", "arbeitgeber",
                  "ort", "first_seen", "last_seen"]
    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                existing[row["refnr"]] = row

    for refnr, info in seen.items():
        if refnr in existing:
            existing[refnr]["last_seen"] = today
        else:
            existing[refnr] = {**info, "first_seen": today, "last_seen": today}

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing.values())

    return existing


def main():
    DATA_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    snapshot_rows = []
    berufe_rows = []
    seen_jobs: dict[str, dict] = {}

    for region, rparams in REGIONS.items():
        print(f"[{region}] Abruf laeuft ...")
        jobs, total = fetch_region(rparams)
        print(f"[{region}] {len(jobs)} von {total} Stellen geladen")

        berufe = Counter()
        arbeitszeit = Counter()
        befristung = Counter()
        arbeitgeber = Counter()

        for j in jobs:
            beruf = (j.get("beruf") or "unbekannt").strip()
            berufe[beruf] += 1
            arbeitgeber[(j.get("arbeitgeber") or "unbekannt").strip()] += 1
            ort = ""
            if isinstance(j.get("arbeitsort"), dict):
                ort = j["arbeitsort"].get("ort") or ""
            refnr = j.get("refnr") or j.get("referenznummer")
            if refnr and refnr not in seen_jobs:
                seen_jobs[refnr] = {
                    "refnr": refnr,
                    "region": region,
                    "beruf": beruf,
                    "titel": (j.get("titel") or "").strip()[:200],
                    "arbeitgeber": (j.get("arbeitgeber") or "").strip()[:150],
                    "ort": ort,
                }

        snapshot_rows.append({
            "datum": today,
            "region": region,
            "stellen_gesamt": total,
            "stellen_geladen": len(jobs),
            "berufe_unique": len(berufe),
            "arbeitgeber_unique": len(arbeitgeber),
            "top_beruf": berufe.most_common(1)[0][0] if berufe else "",
            "top_arbeitgeber": arbeitgeber.most_common(1)[0][0] if arbeitgeber else "",
        })

        for beruf, n in berufe.most_common():
            berufe_rows.append({
                "datum": today, "region": region, "beruf": beruf, "anzahl": n,
            })

    append_csv(DATA_DIR / "snapshots.csv",
               ["datum", "region", "stellen_gesamt", "stellen_geladen",
                "berufe_unique", "arbeitgeber_unique", "top_beruf", "top_arbeitgeber"],
               snapshot_rows)
    append_csv(DATA_DIR / "berufe.csv",
               ["datum", "region", "beruf", "anzahl"],
               berufe_rows)
    log = update_jobs_log(DATA_DIR / "jobs_log.csv", today, seen_jobs)

    print(f"\nFertig. Snapshots: {len(snapshot_rows)} Regionen, "
          f"Stellen-Log: {len(log)} Stellen insgesamt bekannt.")


if __name__ == "__main__":
    main()
