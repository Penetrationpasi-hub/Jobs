#!/usr/bin/env python3
"""
BA-Jobmonitor: Sammelt taeglich Stellenangebote der Bundesagentur fuer Arbeit
fuer 50 km Luftlinie um Waiblingen ueber die Jobsuche-API.

Auth: X-API-Key: jobboerse-jobsuche (oeffentliche clientId, keine Registrierung noetig)
API-Doku: https://github.com/bundesAPI/jobsuche-api

Outputs (im Ordner data/):
  snapshots.csv   - ein Datensatz pro Tag und Region (Gesamtzahlen, Verteilungen)
  berufe.csv      - Anzahl Stellen pro Beruf, Tag und Region (Top-Auswertung)
  jobs_log.csv    - jede jemals gesehene Stelle mit first_seen/last_seen
                    -> ermoeglicht Laufzeit- und Fluktuationsanalysen
  arbeitslose.csv - monatliche Arbeitslose + Quote je Kreis aus der
                    Regionaldatenbank Deutschland (GENESIS, EVAS 13211).
                    Benoetigt env GENESIS_USER / GENESIS_PASS
                    (kostenloses Konto auf regionalstatistik.de).
  scrapjobs_log.csv - Stellen von Karriereseiten (Repo ScrapJobs)
  stellen_alle.csv  - BA + Karriereseiten im gemeinsamen Format, jede
                      Stelle einmal (siehe README)
"""

import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path
from umkreis import (REGION, RADIUS_KM, filter_stellen, im_umkreis,
                     schreibe_pruefung, zeitreihen)

# Die BA hat pc/v4/jobs Anfang August 2026 abgeschaltet (Antwort:
# "403 No match found for request"). Aktuell ist pc/v6/jobs; die
# App-Variante dient als Rueckfall. fetch_page probiert der Reihe nach
# und merkt sich den ersten Endpunkt, der antwortet.
API_ROOT = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service"
API_ENDPOINTS = [f"{API_ROOT}/pc/v6/jobs", f"{API_ROOT}/pc/v4/app/jobs"]
HEADERS = {
    "X-API-Key": "jobboerse-jobsuche",
    "User-Agent": "ba-jobmonitor/1.0 (privates Arbeitsmarkt-Monitoring)",
}

# Ein einziges Suchgebiet fuer die Auswertung (Excel).
REGIONS = {
    REGION: {"wo": "Waiblingen", "umkreis": RADIUS_KM},
}

# Archiv: die alten Suchgebiete (bis 21.11.2026) werden weiter abgefragt,
# aber NUR in data/archiv_*.csv gespeichert, ungefiltert und ohne
# Einfluss auf die Excel. Zweck: lange Historie auch ausserhalb des
# 50-km-Radius (z. B. Aalen/Ostalb), falls sich der Suchraum aendert.
# Abschalten mit ARCHIV=0. Ein Ausfall bricht den Datenlauf nicht ab.
ARCHIV_REGIONS = {
    "waiblingen_30km": {"wo": "Waiblingen", "umkreis": 30},
    "rems-murr-kreis": {"wo": "Backnang", "umkreis": 25},
    "ostalbkreis": {"wo": "Aalen", "umkreis": 30},
    "backnang_10km": {"wo": "Backnang", "umkreis": 10},
    "stuttgart_ost": {"wo": "Fellbach", "umkreis": 8},
}
ARCHIV_AKTIV = os.environ.get("ARCHIV", "1").strip() != "0"
ARCHIV_LOG = "archiv_jobs_log.csv"
ARCHIV_SNAPSHOTS = "archiv_snapshots.csv"
ARCHIV_BERUFE = "archiv_berufe.csv"

PAGE_SIZE = 100
# Sicherheitslimit je Suchgebiet: 300 Seiten x 100 = 30000 Stellen.
# Ein hartes API-Limit ist nicht dokumentiert; macht die API frueher
# dicht (Fehler oder dauerhaft leere Seiten), bricht fetch_region
# sauber ab und behaelt das Teilergebnis.
MAX_PAGES = 300
REQUEST_PAUSE = 1.0     # Sekunden zwischen Requests, hoeflich bleiben
DATA_DIR = Path(__file__).parent / "data"

# ---------------- Regionaldatenbank Deutschland (GENESIS, EVAS 13211)
# Monatliche Arbeitslose und Arbeitslosenquoten auf Kreisebene.
# Kostenloses Konto auf regionalstatistik.de noetig, Zugangsdaten als
# GitHub Secrets GENESIS_USER / GENESIS_PASS. Nur POST, GET ist abgeschaltet.
# Regionaldatenbank Deutschland: Pfad klein geschrieben ("genesisws"),
# anders als bei GENESIS-Online (genesis.destatis.de/genesisWS), das nur
# Bund/Laender hat. Per env GENESIS_BASE umstellbar.
GENESIS_BASE = (os.environ.get("GENESIS_BASE", "").strip()
                or "https://www.regionalstatistik.de/genesisws/rest/2020"
                ).rstrip("/")
# Kreistabelle Arbeitslose/Quoten, Monatswerte. Falls der Code nicht passt,
# listet fetch_arbeitslose() den Katalog und man setzt env AL_TABLE.
AL_TABLE = os.environ.get("AL_TABLE", "13211-01-03-4-B")
AL_KREISE = {
    "08119": "Rems-Murr-Kreis",
    "08136": "Ostalbkreis",
    "08111": "Stuttgart",         # fuer das Suchgebiet Stuttgart Ost
}
# Suchgebiet -> AGS fuer die Kreis-Relation im Excel
REGION_ZU_AGS = {
    "rems-murr-kreis": "08119",
    "ostalbkreis": "08136",
    "waiblingen_30km": "08119",   # Waiblingen liegt im Rems-Murr-Kreis
    "backnang_10km": "08119",
    "stuttgart_ost": "08111",     # Naeherung, Suchgebiet ist Fellbach 8 km
}
AL_CSV = DATA_DIR / "arbeitslose.csv"


def genesis_creds() -> tuple[str, str] | None:
    """Nutzername/Passwort (GENESIS_USER/GENESIS_PASS), sonst API-Token.

    Die Regionaldatenbank verlangt ein Passwort; der Token (als Nutzername
    mit leerem Passwort) reicht nur bei GENESIS-Online (destatis)."""
    user = os.environ.get("GENESIS_USER", "").strip()
    pw = os.environ.get("GENESIS_PASS", "").strip()
    if user and pw:
        return user, pw
    token = os.environ.get("GENESIS_TOKEN", "").strip()
    if token:
        return token, ""
    return None


def genesis_post(endpoint: str, params: dict) -> bytes:
    """POST an die GENESIS-REST-Schnittstelle, Zugangsdaten im Header."""
    user, pw = genesis_creds()
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        f"{GENESIS_BASE}/{endpoint}", data=body, method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "username": user,
            "password": pw,
            "User-Agent": HEADERS["User-Agent"],
        })
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


MONAT_NUM = {f"MONAT{m:02d}": m for m in range(1, 13)}


def parse_zahl(s):
    s = str(s or "").strip()
    if s in ("", "-", ".", "...", "x", "/"):
        return None
    try:
        f = float(s.replace(",", "."))
    except ValueError:
        return None
    return int(f) if f.is_integer() else f


def fetch_arbeitslose():
    """Monatliche Arbeitslose je Kreis aus GENESIS ziehen -> arbeitslose.csv.

    Voller Neuabruf ab Vorjahr bei jedem Lauf (Daten werden revidiert).
    Ohne Zugangsdaten wird der Schritt uebersprungen, das Excel nutzt
    dann den letzten Stand der CSV.
    """
    if genesis_creds() is None:
        print("GENESIS_USER/GENESIS_PASS (oder GENESIS_TOKEN) nicht gesetzt, "
              "Arbeitslosen-Abruf uebersprungen.", file=sys.stderr)
        return
    jahr = date.today().year
    params = {
        "name": AL_TABLE,
        "area": "free",
        "regionalvariable": "KREISE",
        "regionalkey": ",".join(AL_KREISE),
        "startyear": jahr - 1,
        "endyear": jahr,
        "format": "ffcsv",
        "language": "de",
        "compress": "false",
    }
    try:
        raw = genesis_post("data/tablefile", params)
    except Exception as e:
        print(f"GENESIS-Abruf fehlgeschlagen: {e}", file=sys.stderr)
        _genesis_katalog_hinweis()
        return
    text = raw.decode("utf-8-sig", errors="replace")
    if text.lstrip().startswith("{"):
        # Fehlerantwort kommt als JSON (z.B. falscher Tabellencode/Login)
        print(f"GENESIS-Fehlerantwort: {text[:400]}", file=sys.stderr)
        _genesis_katalog_hinweis()
        return

    zeilen = {}   # (jahr, monat, ags) -> {arbeitslose, quote}
    reader = csv.DictReader(text.splitlines(), delimiter=";")
    feld = reader.fieldnames or []
    # Wertspalten tolerant erkennen (Benennungen variieren je Tabelle)
    f_alo = next((f for f in feld
                  if "Arbeitslose" in f and "Anzahl" in f), None)
    f_quote = next((f for f in feld if "quote" in f.lower()
                    and "zivilen" in f.lower()), None) \
        or next((f for f in feld if "quote" in f.lower()), None)
    if not f_alo:
        print(f"Wertspalte nicht gefunden. Spalten: {feld}", file=sys.stderr)
        return
    for row in reader:
        ags = (row.get("1_Auspraegung_Code") or "").strip()
        if ags not in AL_KREISE:
            continue
        try:
            j = int((row.get("Zeit") or "0").strip())
        except ValueError:
            continue
        m = MONAT_NUM.get((row.get("2_Auspraegung_Code") or "").strip())
        if not j or not m:
            continue
        alo = parse_zahl(row.get(f_alo, ""))
        if alo is None:
            continue
        quote = parse_zahl(row.get(f_quote, "")) if f_quote else None
        zeilen[(j, m, ags)] = {"arbeitslose": alo, "quote": quote}

    if not zeilen:
        print("GENESIS: keine verwertbaren Zeilen erhalten.", file=sys.stderr)
        return
    # Bestehende CSV einlesen und mit neuen Monaten zusammenfuehren,
    # damit Historie vor dem Abruffenster erhalten bleibt
    if AL_CSV.exists():
        with AL_CSV.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                k = (int(row["jahr"]), int(row["monat"]), row["ags"])
                zeilen.setdefault(k, {
                    "arbeitslose": parse_zahl(row["arbeitslose"]),
                    "quote": parse_zahl(row["quote"]),
                })
    with AL_CSV.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["jahr", "monat", "ags", "kreis", "arbeitslose", "quote"])
        for (j, m, ags) in sorted(zeilen):
            v = zeilen[(j, m, ags)]
            w.writerow([j, m, ags, AL_KREISE[ags],
                        v["arbeitslose"],
                        "" if v["quote"] is None else v["quote"]])
    print(f"Arbeitslosenzahlen aktualisiert: {len(zeilen)} Zeilen "
          f"({AL_CSV.name}).")


def _genesis_katalog_hinweis():
    """Bei Problemen verfuegbare 13211er-Tabellen listen (Diagnose)."""
    try:
        raw = genesis_post("catalogue/tables", {
            "selection": "13211*", "area": "free",
            "pagelength": 60, "language": "de",
        })
        data = json.loads(raw.decode("utf-8", errors="replace"))
        for t in (data.get("List") or [])[:60]:
            print(f"  Tabelle: {t.get('Code')} - {t.get('Content')}",
                  file=sys.stderr)
        print("Falls noetig: passenden Code als env AL_TABLE setzen.",
              file=sys.stderr)
    except Exception as e:
        print(f"Katalogabruf fehlgeschlagen: {e}", file=sys.stderr)


def lade_arbeitslose():
    """arbeitslose.csv einlesen -> Liste sortierter Monatszeilen."""
    if not AL_CSV.exists():
        return []
    rows = []
    with AL_CSV.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append({
                "jahr": int(row["jahr"]), "monat": int(row["monat"]),
                "ags": row["ags"], "kreis": row["kreis"],
                "arbeitslose": parse_zahl(row["arbeitslose"]),
                "quote": parse_zahl(row["quote"]),
            })
    rows.sort(key=lambda r: (r["jahr"], r["monat"], r["ags"]))
    return rows


def fetch_page(params: dict) -> dict | None:
    """Eine Ergebnisseite laden. Liefert None statt einer Exception,
    wenn nach 3 Versuchen nichts kommt -- der Aufrufer entscheidet, ob
    das ein API-Limit (Teilergebnis behalten) oder ein Ausfall ist."""
    qs = urllib.parse.urlencode(params)
    for attempt in range(3):
        for base in list(API_ENDPOINTS):
            req = urllib.request.Request(f"{base}?{qs}", headers=HEADERS)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                print(f"  Fehler {base.rsplit('/jobsuche-service/', 1)[-1]} "
                      f"(Versuch {attempt + 1}/3): {e}", file=sys.stderr)
                continue
            if base != API_ENDPOINTS[0]:
                # funktionierenden Endpunkt fuer alle weiteren Seiten vorziehen
                API_ENDPOINTS.remove(base)
                API_ENDPOINTS.insert(0, base)
            return data
        time.sleep(5 * (attempt + 1))
    print(f"  Aufgegeben: {params.get('wo')} Seite {params.get('page')}",
          file=sys.stderr)
    return None


def normalisiere_stelle(j: dict) -> dict:
    """v6 liefert je nach Auslieferung die alten Feldnamen (refnr, beruf,
    arbeitgeber, arbeitsort) oder neue (referenznummer, hauptberuf, firma,
    stellenlokationen). Hier auf die alten abbilden, damit Logs und Excel
    unveraendert weiterlaufen."""
    out = dict(j)
    out["refnr"] = j.get("refnr") or j.get("referenznummer")
    out["beruf"] = j.get("beruf") or j.get("hauptberuf")
    out["titel"] = j.get("titel") or j.get("stellenangebotsTitel")
    out["arbeitgeber"] = j.get("arbeitgeber") or j.get("firma")
    if not isinstance(j.get("arbeitsort"), dict):
        lok = j.get("stellenlokationen") or [{}]
        adr = (lok[0] or {}).get("adresse") if isinstance(lok[0], dict) else None
        out["arbeitsort"] = adr if isinstance(adr, dict) else {}
    return out


def fetch_region(region_params: dict) -> tuple[list[dict], int]:
    """Alle Stellen einer Region einsammeln (paginiert).

    Tolerant gegen ein API-seitiges Paginierungslimit: schlaegt eine
    Seite > 1 dauerhaft fehl, wird abgebrochen und das Teilergebnis
    behalten. Nur wenn schon Seite 1 scheitert, fliegt eine Exception.
    Dubletten ueber Seitengrenzen (die Sortierung kann bei laufenden
    Aenderungen verrutschen) werden per refnr uebersprungen.
    """
    jobs = []
    refs: set[str] = set()
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
        if data is None:
            if page == 1:
                raise RuntimeError(f"Seite 1 nicht abrufbar: {region_params}")
            print(f"  Stopp bei Seite {page} (moegliches API-Limit), "
                  f"behalte {len(jobs)} Stellen.", file=sys.stderr)
            break
        max_ergebnisse = int(data.get("maxErgebnisse", 0) or 0) or max_ergebnisse
        batch = data.get("stellenangebote") or data.get("ergebnisliste") or []
        if not batch:
            break
        for j in map(normalisiere_stelle, batch):
            ref = j.get("refnr") or j.get("referenznummer")
            if ref:
                if ref in refs:
                    continue
                refs.add(ref)
            jobs.append(j)
        if max_ergebnisse and len(jobs) >= max_ergebnisse:
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
            # Aktuelle Orts-/Berufsdaten fuer den Filter; urspruengliches
            # Suchgebiet und first_seen bleiben als Herkunft erhalten.
            existing[refnr].update({k: v for k, v in info.items() if k != "region"})
            existing[refnr]["last_seen"] = today
        else:
            existing[refnr] = {**info, "first_seen": today, "last_seen": today}

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(existing.values())

    return existing


def update_beobachtungen(today, seen):
    """Tagesgenaue Detaildaten; ein erneuter Tageslauf ersetzt diesen Tag."""
    path = DATA_DIR / "jobs_beobachtungen.csv"
    fields = ["datum", "refnr", "beruf", "arbeitgeber", "ort"]
    rows = []
    if path.exists():
        with path.open(encoding="utf-8", newline="") as f:
            rows = [r for r in csv.DictReader(f) if r["datum"] != today]
    rows.extend({"datum": today, **{k: r[k] for k in fields[1:]}}
                for r in seen.values())
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


# ---------------- ScrapJobs: Karriereseiten regionaler Arbeitgeber
# Das Schwester-Repo Penetrationpasi-hub/ScrapJobs liest taeglich die
# Karriereseiten ausgewaehlter Arbeitgeber und legt stellen.json ab.
# Die Stellen kommen NICHT in die BA-Zahlen (Zeitreihe, Berufe,
# Branchen), sondern in eigene Blaetter: sonst Doppelzaehlung, und die
# Daten haben kein Berufsfeld. Ein Ausfall bricht den Lauf nicht ab.
SCRAPJOBS_URL = (os.environ.get("SCRAPJOBS_URL", "").strip()
                 or "https://raw.githubusercontent.com/"
                    "Penetrationpasi-hub/ScrapJobs/main/stellen.json")
SCRAPJOBS_FIELDS = ["id", "quelle", "arbeitgeber", "titel", "ort", "url",
                    "veroeffentlicht", "first_seen", "last_seen", "aktiv"]
# Stand der zuletzt gelesenen stellen.json (fuer die Zusammenfassung)
SCRAPJOBS_STAND = "scrapjobs_stand.json"
# aelter als das: Warnung im Actions-Log (ScrapJobs-Lauf ausgefallen?)
SCRAPJOBS_MAX_ALTER_TAGE = 2


def lade_scrapjobs_json():
    """stellen.json holen; SCRAPJOBS_URL darf auch ein lokaler Pfad sein."""
    if not SCRAPJOBS_URL.startswith("http"):
        with open(SCRAPJOBS_URL, encoding="utf-8") as f:
            return json.load(f)
    req = urllib.request.Request(SCRAPJOBS_URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def update_scrapjobs(today: str):
    """data/scrapjobs_log.csv fortschreiben (id -> first_seen/last_seen).

    first_seen/last_seen kommen aus ScrapJobs selbst (erstmalsGesehen,
    zuletztGesehen), nicht vom Abrufdatum: ist stellen.json veraltet, weil
    der ScrapJobs-Lauf ausfiel, gilt eine Stelle sonst faelschlich als
    'heute gesehen'. aktiv = steht in der aktuellen stellen.json.
    """
    path = DATA_DIR / "scrapjobs_log.csv"
    try:
        doc = lade_scrapjobs_json()
        stellen = doc["stellen"]
    except Exception as e:
        print(f"[scrapjobs] Abruf fehlgeschlagen, uebersprungen: {e}",
              file=sys.stderr)
        return
    stand = (doc.get("aktualisiert") or "")[:10] or today
    quellen = doc.get("quellen") or []
    alter = (date.fromisoformat(today) - date.fromisoformat(stand)).days
    if alter > SCRAPJOBS_MAX_ALTER_TAGE:
        print(f"::warning::ScrapJobs-Daten sind {alter} Tage alt (Stand "
              f"{stand}) - Lauf im Repo ScrapJobs pruefen.", file=sys.stderr)

    existing: dict[str, dict] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                row["aktiv"] = "nein"
                # Reparatur: last_seen kann nie juenger als die Quelle sein
                # (alte Laeufe schrieben hier das Abrufdatum hinein)
                row["last_seen"] = min(row["last_seen"], stand)
                row["first_seen"] = min(row["first_seen"], row["last_seen"])
                existing[row["id"]] = row
    for s in stellen:
        if not im_umkreis(s.get("location") or ""):
            continue
        sid = s.get("id") or s.get("url")
        if not sid:
            continue
        erst = s.get("erstmalsGesehen") or stand
        zuletzt = s.get("zuletztGesehen") or stand
        row = existing.setdefault(sid, {"id": sid, "first_seen": erst})
        row.update({
            "quelle": s.get("sourceLabel") or s.get("source") or "",
            "arbeitgeber": (s.get("company") or "").strip()[:150],
            "titel": (s.get("title") or "").strip()[:200],
            "ort": (s.get("location") or "").strip()[:100],
            "url": s.get("url") or "",
            "veroeffentlicht": s.get("posted") or "",
            "first_seen": min(row["first_seen"], erst),
            "last_seen": zuletzt,
            "aktiv": "ja",
        })
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCRAPJOBS_FIELDS)
        w.writeheader()
        w.writerows(existing.values())
    (DATA_DIR / SCRAPJOBS_STAND).write_text(json.dumps({
        "aktualisiert": doc.get("aktualisiert"),
        "abgerufen": today,
        "quellen_gesamt": len(quellen),
        "quellen_ok": sum(1 for q in quellen if q.get("status") == "done"),
        "stellen": len(stellen),
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[scrapjobs] {len(stellen)} Stellen abgerufen (Stand {stand}), "
          f"{len(existing)} im Log")


def sammle(regions: dict, nur_umkreis: bool):
    """Suchgebiete abfragen. Liefert (snapshot_rows, berufe_rows, seen).

    nur_umkreis=True: nur Stellen mit Arbeitsort im 50-km-Radius
    (Auswertung). False: alles, was die Suche liefert (Archiv)."""
    today = date.today().isoformat()
    snapshot_rows, berufe_rows = [], []
    seen_jobs: dict[str, dict] = {}
    for region, rparams in regions.items():
        print(f"[{region}] Abruf laeuft ...")
        try:
            jobs, total = fetch_region(rparams)
        except Exception as e:
            # Region ueberspringen statt den ganzen Lauf zu reissen; der
            # Tag bleibt in der Zeitreihe dann leer (kein falsches 0)
            print(f"[{region}] Abruf fehlgeschlagen, uebersprungen: {e}",
                  file=sys.stderr)
            continue
        print(f"[{region}] {len(jobs)} von {total} Stellen geladen")
        if total > len(jobs):
            print(f"[{region}] Hinweis: Detaildaten unvollstaendig "
                  f"({len(jobs)}/{total}).", file=sys.stderr)

        if nur_umkreis:
            jobs = [j for j in jobs
                    if im_umkreis((j.get("arbeitsort") or {}).get("ort", ""))]
            print(f"[{region}] {len(jobs)} Stellen mit Arbeitsort im "
                  "50-km-Radius")

        berufe = Counter()
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
    return snapshot_rows, berufe_rows, seen_jobs


SNAPSHOT_FELDER = ["datum", "region", "stellen_gesamt", "stellen_geladen",
                   "berufe_unique", "arbeitgeber_unique", "top_beruf",
                   "top_arbeitgeber"]


def archiv_start():
    """Archiv-Log beim ersten Lauf mit den Altdaten der alten Suchgebiete
    aus jobs_log.csv anlegen, damit first_seen ab Juli 2026 erhalten
    bleibt und noch offene Stellen nahtlos weiterlaufen."""
    ziel = DATA_DIR / ARCHIV_LOG
    quelle = DATA_DIR / "jobs_log.csv"
    if ziel.exists() or not quelle.exists():
        return
    with quelle.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("region") in ARCHIV_REGIONS]
        felder = reader.fieldnames
    with ziel.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(rows)
    print(f"[archiv] {ARCHIV_LOG} mit {len(rows)} Altstellen angelegt")


def sammle_archiv(today: str):
    """Alte Suchgebiete abfragen und nur ins Archiv schreiben."""
    if not ARCHIV_AKTIV:
        print("[archiv] abgeschaltet (ARCHIV=0)")
        return
    try:
        archiv_start()
        snaps, berufe, seen = sammle(ARCHIV_REGIONS, nur_umkreis=False)
        if not snaps:
            print("[archiv] kein Suchgebiet abrufbar, nichts gespeichert",
                  file=sys.stderr)
            return
        append_csv(DATA_DIR / ARCHIV_SNAPSHOTS, SNAPSHOT_FELDER, snaps)
        append_csv(DATA_DIR / ARCHIV_BERUFE,
                   ["datum", "region", "beruf", "anzahl"], berufe)
        log = update_jobs_log(DATA_DIR / ARCHIV_LOG, today, seen)
        print(f"[archiv] {len(seen)} Stellen heute, {len(log)} im Archiv")
    except Exception as e:
        print(f"::warning::Archiv-Abfrage fehlgeschlagen: {e}",
              file=sys.stderr)


def main():
    DATA_DIR.mkdir(exist_ok=True)
    today = date.today().isoformat()
    snapshot_rows, berufe_rows, seen_jobs = sammle(REGIONS, nur_umkreis=True)

    append_csv(DATA_DIR / "snapshots.csv", SNAPSHOT_FELDER, snapshot_rows)
    append_csv(DATA_DIR / "berufe.csv",
               ["datum", "region", "beruf", "anzahl"],
               berufe_rows)
    log = update_jobs_log(DATA_DIR / "jobs_log.csv", today, seen_jobs)
    if snapshot_rows:
        update_beobachtungen(today, seen_jobs)

    fetch_arbeitslose()
    update_scrapjobs(today)
    try:
        import api_quellen
        api_quellen.sammle(today, DATA_DIR)
    except Exception as e:      # Boersen-Stichprobe darf den Lauf nie stoppen
        print(f"[api] uebersprungen: {e}", file=sys.stderr)
    sammle_archiv(today)

    if not snapshot_rows:
        # Kein einziges Suchgebiet geladen: rot werden statt still eine
        # unveraenderte Excel zu committen (so blieb der v4-Ausfall von
        # August bis Oktober unbemerkt).
        print("::error::Kein Suchgebiet abrufbar - BA-API pruefen.",
              file=sys.stderr)
        sys.exit(1)

    print(f"\nFertig. Snapshots: {len(snapshot_rows)} Regionen, "
          f"Stellen-Log: {len(log)} Stellen insgesamt bekannt.")




# ==================================================================
# Teil 2: Auswertung -> arbeitsmarkt_auswertung.xlsx
# ==================================================================

import csv
import os
import re
import statistics
from datetime import date, datetime

from openpyxl import Workbook
from branchen import (HAUPTGRUPPEN, SEGMENT_KURZ, SEGMENTE, SEKTOREN,
                      SONSTIGE, branche_von_beruf, einordnung)
from orte import kreis_von
from openpyxl.chart import AreaChart, BarChart, LineChart, Reference
from openpyxl.chart.marker import DataPoint
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule
from openpyxl.chart.axis import ChartLines
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "arbeitsmarkt_auswertung.xlsx")

REGION_NAMEN = {
    REGION: "Waiblingen 50 km (Luftlinie)",
    "waiblingen_15km": "Waiblingen 15 km (alt)",
    "waiblingen_30km": "Waiblingen 30 km",
    "rems-murr-kreis": "Rems-Murr-Kreis",
    "ostalbkreis": "Ostalbkreis",
    "backnang_10km": "Backnang 10 km",
    "stuttgart_ost": "Stuttgart Ost (Fellbach 8 km)",
}

# ---- Umfang der Blaetter. None = unbegrenzt (alle Eintraege). ------
# Aktuell, Standzeit, Arbeitgeber und Arbeitgeber-Tempo zeigen ALLES.
# Berufe-Zeitreihe legt je Beruf eine eigene SPALTE an und bleibt
# deshalb gedeckelt (None geht auch, macht das Blatt nur sehr breit).
# AL-Relation ist das Blatt mit manueller Eingabe, dort reichen 20.
TOP_BERUFE_ZEITREIHE = 50
TOP_AL_RELATION = 20
# Arbeitgeber-Tempo: mindestens so viele beendete Stellen noetig,
# sonst dominieren Einzelfaelle die Rangliste
AG_TEMPO_MIN_BEENDET = 5

ARIAL = "Arial"
HEAD_FONT = Font(name=ARIAL, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", start_color="1D3C6E")
INPUT_FONT = Font(name=ARIAL, color="0000FF")
DATUM_FMT = "DD.MM.YYYY"


_RECHTSFORM = re.compile(
    r"\b(gmbh|mbh|co|kg|ag|se|ohg|ug|gg?mbh|e\.?\s?v|a[oö]r|eg|srl|b\.?v)\b")
_GENDER = re.compile(r"\(?\b[mwdfix](?:\s*/\s*[mwdfix]){1,2}\)?", re.I)


def norm_ag(x):
    """Arbeitgebername ohne Rechtsform/Sonderzeichen (Abgleich BA <-> Karriereseite)."""
    x = _RECHTSFORM.sub(" ", (x or "").lower().replace("&", " "))
    return re.sub(r"[^a-zäöüß0-9]", "", x)


def norm_titel(x):
    x = _GENDER.sub(" ", (x or "").lower())
    return re.sub(r"[^a-zäöüß0-9]", "", x)


def ag_passt(a, b):
    """Gleicher Arbeitgeber, wenn ein Name im anderen enthalten ist (min. 6 Zeichen)."""
    return len(a) >= 6 and len(b) >= 6 and (a in b or b in a)


def read_csv(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def as_date(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def standzeit_tage(r):
    """Standzeit einer Log-Zeile in Tagen (erster Tag zaehlt mit)."""
    return (as_date(r["last_seen"]) - as_date(r["first_seen"])).days + 1


def ba_ist_offen(r, stand):
    # Tagesbeobachtungen haben Vorrang, insbesondere bei Wiederholungsläufen.
    return r.get("_offen", r["last_seen"] == stand)


# ---------------- Gemeinsames Format BA + Karriereseiten (ScrapJobs)
ALLE_FIELDS = ["stellen_id", "herkunft", "ba_refnr", "scrapjobs_id",
               "titel", "arbeitgeber", "ort", "kreis", "ba_suchgebiet",
               "beruf", "beruf_quelle", "branche", "branche_quelle",
               "hauptgruppe", "url", "first_seen", "last_seen", "offen", "standzeit_tage"]
HERKUNFT_BA = "BA"
HERKUNFT_SJ = "Karriereseite"
HERKUNFT_BEIDE = "beide"
# Eine Karriereseiten-Stelle gilt als dieselbe wie eine BA-Stelle, wenn
# Arbeitgeber und Titel passen und sich die Zeitraeume bis auf so viele
# Tage beruehren (sonst wuerde eine laengst beendete BA-Anzeige mit
# gleichem Titel eine neue Karriereseiten-Anzeige "schlucken").
ABGLEICH_TOLERANZ_TAGE = 14


def baue_stellen_alle(log, sj, ba_stand):
    """BA-Log und ScrapJobs-Log in ein gemeinsames Format bringen.

    Jede Stelle genau eine Zeile; dieselbe Stelle bei BA und auf der
    Karriereseite wird zu einer Zeile mit herkunft='beide'. Karriereseiten-
    Stellen bekommen Beruf (ueber gleichen Titel in den BA-Daten) und
    Branche, alle Stellen einen Kreis (orte.kreis_von). Ergebnis wird
    nach data/stellen_alle.csv geschrieben und zurueckgegeben.
    """
    # Vor dem Quellenabgleich filtern: ein auswaertiger Treffer darf keine
    # lokale Karriereseiten-Stelle schlucken (oder umgekehrt).
    log, sj = filter_stellen(log), filter_stellen(sj)
    # BA-Index: Arbeitgeber-Schluessel -> Titel-Schluessel -> BA-Zeilen
    ba_idx = {}
    titel_beruf = {}
    ag_branche = {}
    for r in log:
        k = norm_ag(r["arbeitgeber"])
        t = norm_titel(r["titel"])
        ba_idx.setdefault(k, {}).setdefault(t, []).append(r)
        if r["beruf"] and r["beruf"] != "unbekannt":
            titel_beruf.setdefault(t, Counter())[r["beruf"]] += 1
        ag_branche.setdefault(k, Counter())[einordnung(r["beruf"]).hauptgruppe] += 1
    ba_keys = [k for k in ba_idx if len(k) >= 6]
    key_cache = {}

    def passende_keys(name):
        k = norm_ag(name)
        if k not in key_cache:
            key_cache[k] = [b for b in ba_keys if ag_passt(k, b)]
        return key_cache[k]

    verbraucht = set()
    partner = {}        # scrapjobs id -> BA-Zeile
    for r in sorted(sj, key=lambda r: r["first_seen"]):
        t = norm_titel(r["titel"])
        if not t:
            continue
        sj_von = as_date(r["first_seen"])
        sj_bis = as_date(r["last_seen"])
        kandidaten = []
        for k in passende_keys(r["arbeitgeber"]):
            for b in ba_idx[k].get(t, ()):
                if b["refnr"] in verbraucht:
                    continue
                luecke = max((sj_von - as_date(b["last_seen"])).days,
                             (as_date(b["first_seen"]) - sj_bis).days, 0)
                if luecke <= ABGLEICH_TOLERANZ_TAGE:
                    kandidaten.append((luecke, not ba_ist_offen(b, ba_stand),
                                       b["refnr"], b))
        if kandidaten:
            b = min(kandidaten, key=lambda x: x[:3])[3]
            verbraucht.add(b["refnr"])
            partner[r["id"]] = b

    def zeile(ba=None, s=None):
        quelle = ba or s
        first = min(x["first_seen"] for x in (ba, s) if x)
        last = max(x["last_seen"] for x in (ba, s) if x)
        offen = bool((ba and ba_ist_offen(ba, ba_stand))
                     or (s and s.get("aktiv", "ja") == "ja"))
        if ba:
            beruf, beruf_q = ba["beruf"], HERKUNFT_BA
        else:
            c = titel_beruf.get(norm_titel(s["titel"]))
            beruf, beruf_q = ((c.most_common(1)[0][0], "Titel-Abgleich")
                              if c else ("", "offen"))
        # Branche = BA-Berufssegment (branchen.py); Reihenfolge der Quellen:
        # Beruf -> Stichwoerter im Titel -> uebliche Hauptgruppe des Arbeitgebers
        hg, branche_q = "", "offen"
        if beruf and beruf != "unbekannt":
            hg = einordnung(beruf).hauptgruppe
            branche_q = "Beruf" if hg else "offen"
        if not hg and s:
            hg = einordnung(s["titel"]).hauptgruppe
            if hg:
                branche_q = "Titel"
            else:
                c = Counter()
                for k in passende_keys(s["arbeitgeber"]):
                    c.update(ag_branche[k])
                c.pop("", None)
                if c:
                    hg, branche_q = c.most_common(1)[0][0], "Arbeitgeber"
        branche = (SEGMENTE[HAUPTGRUPPEN[hg][1]] if hg in HAUPTGRUPPEN
                   else SONSTIGE)
        ort = (ba or {}).get("ort") or (s or {}).get("ort") or ""
        return {
            "stellen_id": f"BA:{ba['refnr']}" if ba else f"SJ:{s['id']}",
            "herkunft": (HERKUNFT_BEIDE if ba and s else
                         HERKUNFT_BA if ba else HERKUNFT_SJ),
            "ba_refnr": ba["refnr"] if ba else "",
            "scrapjobs_id": s["id"] if s else "",
            "titel": quelle["titel"],
            "arbeitgeber": quelle["arbeitgeber"],
            "ort": ort,
            "kreis": kreis_von(ort),
            "ba_suchgebiet": ba["region"] if ba else "",
            "beruf": beruf,
            "beruf_quelle": beruf_q,
            "branche": branche,
            "branche_quelle": branche_q,
            "hauptgruppe": hg,
            "url": (s or {}).get("url") or "",
            "first_seen": first,
            "last_seen": last,
            "offen": "ja" if offen else "nein",
            "standzeit_tage": (as_date(last) - as_date(first)).days + 1,
        }

    sj_zu_ba = {b["refnr"]: sid for sid, b in partner.items()}
    sj_map = {r["id"]: r for r in sj}
    alle = []
    for b in log:
        sid = sj_zu_ba.get(b["refnr"])
        alle.append(zeile(b, sj_map[sid] if sid else None))
    for r in sj:
        if r["id"] not in partner:
            alle.append(zeile(None, r))
    with open(os.path.join(DATA, "stellen_alle.csv"), "w",
              newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=ALLE_FIELDS)
        w.writeheader()
        w.writerows(alle)
    return alle


def boersen_zeilen(api, ba_log):
    """Boersen-Stichprobe (api_jobs_log.csv) gegen die BA-Stellen abgleichen.

    Gleiche Stelle = gleicher Arbeitgeber (ag_passt) und gleicher Titel
    (norm_titel), egal wann gesehen. Nur im Umkreis. Rueckgabe: Liste
    von Dicts mit zusaetzlich 'auch_bei_ba' ('ja'/'nein') und 'branche'.
    Die Stichprobe steht nur in ihrem eigenen Blatt und fliesst nicht in
    BA-Summen oder Zeitreihen ein.
    """
    ba_idx = {}
    for r in ba_log:
        ba_idx.setdefault(norm_ag(r["arbeitgeber"]), set()).add(norm_titel(r["titel"]))
    ba_keys = [k for k in ba_idx if len(k) >= 6]
    out = []
    for r in filter_stellen(api):
        t = norm_titel(r["titel"])
        k = norm_ag(r["arbeitgeber"])
        auch = bool(t) and any(t in ba_idx[b] for b in ba_keys if ag_passt(k, b))
        hg = einordnung(r["titel"]).hauptgruppe
        branche = (SEGMENTE[HAUPTGRUPPEN[hg][1]] if hg in HAUPTGRUPPEN
                   else SONSTIGE)
        out.append({**r, "auch_bei_ba": "ja" if auch else "nein",
                    "branche": branche})
    return out


def style_header(ws, ncols, row=1):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row, column=c)
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    if row == 1:
        ws.freeze_panes = "A2"


def autosize(ws, maxw=45):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 2, maxw)


def base_font(ws):
    for row in ws.iter_rows():
        for c in row:
            if c.font is None or c.font.name != ARIAL:
                c.font = Font(name=ARIAL, bold=c.font.bold if c.font else False,
                              color=c.font.color if c.font else None)


# ---- Diagramm-Helfer: 2D statt der alten 3D-Flaechen. --------------
# Bei den AreaChart3D verdeckte die vorderste Flaeche alle kleineren
# Reihen, und die Zeitachse war in der 3D-Perspektive unlesbar.

def _achsen_sichtbar(ch, x_titel=None, y_titel=None,
                     x_fmt=None, y_fmt="#,##0"):
    # Excel unterdrueckt Achsen, wenn delete nicht explizit False ist
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    if x_titel:
        ch.x_axis.title = x_titel
    if y_titel:
        ch.y_axis.title = y_titel
    if x_fmt:
        ch.x_axis.number_format = x_fmt
    if y_fmt:
        ch.y_axis.number_format = y_fmt
    ch.y_axis.majorGridlines = ChartLines()
    ch.legend.position = "b"


def linien_chart(titel, x_titel, y_titel, x_fmt, n_kategorien,
                 hoehe=10, breite=22):
    """Liniendiagramm fuer Zeitreihen: jede Reihe bleibt sichtbar."""
    ch = LineChart()
    ch.title = titel
    ch.height, ch.width = hoehe, breite
    _achsen_sichtbar(ch, x_titel, y_titel, x_fmt)
    # Datumsbeschriftung ausduennen, sonst wird die Achse bei vielen
    # Erhebungstagen unleserlich (~12 Beschriftungen sind gut lesbar)
    skip = max(1, n_kategorien // 12)
    ch.x_axis.tickLblSkip = skip
    ch.x_axis.tickMarkSkip = skip
    return ch


def balken_chart(titel, wert_titel, n_zeilen, hoehe=None, breite=22):
    """Horizontales Balkendiagramm: lange Namen bleiben lesbar,
    kleine Werte verschwinden nicht hinter grossen."""
    ch = BarChart()
    ch.type = "bar"
    ch.grouping = "clustered"
    ch.gapWidth = 60
    ch.title = titel
    ch.height = hoehe if hoehe else max(8.0, min(26.0, 1 + 0.75 * n_zeilen))
    ch.width = breite
    _achsen_sichtbar(ch, None, wert_titel)
    # Rang 1 oben statt unten (Excel zeichnet Kategorien von unten nach
    # oben); Wertachse dabei unten am Diagramm lassen
    ch.x_axis.scaling.orientation = "maxMin"
    ch.y_axis.crosses = "max"
    return ch


def build_excel():
    raw_snaps = read_csv("snapshots.csv")
    raw_log = read_csv("jobs_log.csv")
    raw_sj = read_csv("scrapjobs_log.csv")
    log, sj = filter_stellen(raw_log), filter_stellen(raw_sj)
    if not raw_snaps:
        print("FEHLER: keine Daten gefunden, zuerst collect_jobs.py laufen lassen.")
        return 1

    schreibe_pruefung(raw_log, raw_sj, os.path.join(DATA, "umkreis_pruefung.csv"))
    berufe, snaps = zeitreihen(log, raw_snaps, read_csv("jobs_beobachtungen.csv"))
    for name, rows, fields in (
        ("snapshots_50km.csv", snaps,
         ["datum", "region", "stellen_gesamt", "stellen_geladen", "methode"]),
        ("berufe_50km.csv", berufe, ["datum", "region", "beruf", "anzahl"]),
    ):
        with open(os.path.join(DATA, name), "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    daten = sorted({r["datum"] for r in snaps})
    stand = daten[-1]
    if any(r["datum"] == stand and r["region"] == REGION for r in raw_snaps):
        aktuelle_refs = {r["refnr"] for r in read_csv("jobs_beobachtungen.csv")
                         if r["datum"] == stand}
        for r in log:
            r["_offen"] = r["refnr"] in aktuelle_refs
    stand_d = as_date(stand)
    snap_map = {(s["datum"], s["region"]): int(s["stellen_gesamt"]) for s in snaps}
    # Aktive Suchgebiete (am Stichtag erhoben) zuerst, eingestellte ans Ende
    alle_reg = sorted({r["region"] for r in berufe} | {s["region"] for s in snaps})
    aktiv = [r for r in alle_reg if (stand, r) in snap_map]
    regionen = aktiv + [r for r in alle_reg if r not in aktiv]
    reg_name = lambda r: REGION_NAMEN.get(r, r)

    # Vergleichsdaten: naechster vorhandener Stichtag ca. 7 bzw. 30 Tage zurueck
    def vergleich(tage):
        ziel = [d for d in daten if (stand_d - as_date(d)).days >= tage]
        return ziel[-1] if ziel else None
    d7, d30 = vergleich(7), vergleich(30)

    # Bestaende je (datum, region, beruf) und je (datum, beruf) gesamt
    brb = {}
    for r in berufe:
        brb[(r["datum"], r["region"], r["beruf"])] = int(r["anzahl"])
    # ueber brb (dedupliziert) aggregieren: schuetzt vor Doppelzaehlung,
    # falls die Erhebung an einem Tag mehrfach lief
    bges = {}
    for (d, _rg, b), n in brb.items():
        bges[(d, b)] = bges.get((d, b), 0) + n

    top_akt = sorted((b for (d, b) in bges if d == stand),
                     key=lambda b: -bges[(stand, b)])
    # frueher Top 20/40 -- jetzt zeigt Aktuell ALLE Berufe des Stichtags,
    # nur das Spalten-Blatt und das Eingabe-Blatt bleiben begrenzt
    bz_berufe = top_akt if TOP_BERUFE_ZEITREIHE is None \
        else top_akt[:TOP_BERUFE_ZEITREIHE]
    al_berufe = top_akt if TOP_AL_RELATION is None \
        else top_akt[:TOP_AL_RELATION]

    wb = Workbook()

    # ---------------- Zusammenfassung
    zs = wb.active
    zs.title = "Zusammenfassung"
    zs["A1"] = "Arbeitsmarkt-Auswertung: 50 km Luftlinie um Waiblingen"
    zs["A1"].font = Font(name=ARIAL, bold=True, size=14)
    zs["A2"] = "Stand"
    zs["B2"] = stand_d
    zs["B2"].number_format = DATUM_FMT
    zs["A3"] = "Erhebungstage"
    zs["B3"] = len(daten)
    zs["A4"] = "Regionen"
    zs["B4"] = ", ".join(reg_name(r) for r in regionen)
    zs["A5"] = "Stellen je gesehen (Log)"
    zs["B5"] = len(log)
    zs["A7"] = ("Arbeitsortfilter: maximal 50 km Luftlinie um Waiblingen "
                "(48.8324, 9.3164), anhand Orts-/PLZ-Koordinaten von GeoNames. "
                "Unklare Orte werden ausgeschlossen; Pruefliste: data/umkreis_pruefung.csv. "
                "Die Zahlen zaehlen geladene Stellen, ohne Hochrechnung auf API-Gesamtzahlen.")
    zs["A8"] = ("Arbeitslose je Beruf fuer das Blatt AL-Relation weiterhin "
                 "manuell aus statistik.arbeitsagentur.de eintragen (blaue "
                 "Spalte). Kreiszahlen kommen automatisch aus der "
                 "Regionaldatenbank Deutschland (Blatt Arbeitslose). "
                 "Kreis-/Agenturstatistiken sind Vergleichsdaten und decken "
                 "nicht den 50-km-Radius ab; manuelle Relationen nur bei gleichem Raumbezug.")
    zs["A9"] = ("Alte Zeitreihen sind aus first_seen/last_seen rekonstruierte "
                "Naeherungen (angenommene durchgehende Sichtbarkeit, damalige "
                "Suchabdeckung unvollstaendig). Neue 50-km-Laeufe verwenden "
                "Tagesbeobachtungen. Methodenwechsel siehe Zeitreihe; "
                "Veraenderungen koennen durch die Suchumstellung entstehen. "
                "Alte Rohdaten bleiben unveraendert erhalten.")
    zs["A10"] = ("Alle Zahlen sind beim Erzeugen fest berechnet (keine "
                 "Formeln), damit sie auch in Vorschau-Apps und auf dem "
                 "Handy angezeigt werden. Einzige Ausnahme: die Relation "
                 "zur blauen Eingabespalte in AL-Relation rechnet live.")
    for c in ("A2", "A3", "A4", "A5"):
        zs[c].font = Font(name=ARIAL, bold=True)

    # ---------------- Zeitreihe (gefiltert, Datengrundlage je Tag ausgewiesen)
    zt = wb.create_sheet("Zeitreihe")
    n_akt = len(aktiv)
    alt_reg = regionen[n_akt:]
    zt.append(["Datum"] + [reg_name(r) for r in aktiv] + ["Stellen im Radius"]
              + [reg_name(r) for r in alt_reg] + ["Datengrundlage"])
    for i, d in enumerate(daten, start=2):
        zt.cell(row=i, column=1, value=as_date(d)).number_format = DATUM_FMT
        werte = []
        for j, r in enumerate(aktiv, start=2):
            v = snap_map.get((d, r))
            zt.cell(row=i, column=j, value=v)
            if v is not None:
                werte.append(v)
        # Summe nur ueber aktive Gebiete -> Reihe bleibt ueber die Zeit
        # vergleichbar, auch wenn ein Suchgebiet eingestellt wurde
        zt.cell(row=i, column=n_akt + 2, value=sum(werte) if werte else None)
        for j, r in enumerate(alt_reg, start=n_akt + 3):
            zt.cell(row=i, column=j, value=snap_map.get((d, r)))
        zt.cell(row=i, column=len(regionen) + 3, value=snaps[i - 2]["methode"])
    style_header(zt, len(regionen) + 3)
    for row in zt.iter_rows(min_row=2, min_col=2):
        for c in row:
            c.number_format = "#,##0"
    ch = linien_chart("Offene Stellen je Suchgebiet", "Datum", "Stellen",
                      "DD.MM.", len(daten))
    # nur die Suchgebiete als Linien; die Summe wuerde die Skala strecken
    # und die einzelnen Gebiete optisch plattdruecken
    ch.add_data(Reference(zt, min_col=2, max_col=n_akt + 1,
                          min_row=1, max_row=len(daten) + 1),
                titles_from_data=True)
    ch.set_categories(Reference(zt, min_col=1, min_row=2,
                                max_row=len(daten) + 1))
    zt.add_chart(ch, f"A{len(daten) + 4}")

    # ---------------- Berufe-Zeitreihe (je Beruf eine Spalte, deshalb
    #                  auf TOP_BERUFE_ZEITREIHE begrenzt)
    bz = wb.create_sheet("Berufe-Zeitreihe")
    bz.append(["Datum"] + bz_berufe)
    for i, d in enumerate(daten, start=2):
        bz.cell(row=i, column=1, value=as_date(d)).number_format = DATUM_FMT
        for j, b in enumerate(bz_berufe, start=2):
            bz.cell(row=i, column=j, value=bges.get((d, b)))
    style_header(bz, len(bz_berufe) + 1)

    # ---------------- Gemeinsamer Bestand BA + Karriereseiten (wird fuer
    # die Branchenauswertung und die Blaetter weiter unten gebraucht)
    alle = baue_stellen_alle(log, sj, stand)

    # ---------------- Branchen = offizielle BA-Berufssegmente (KldB 2010)
    # Ausschliesslich gefilterte Einzelstellen; keine Hochrechnung der
    # alten, raeumlich unpassenden Suchgebietssummen.
    basis = [REGION]
    seg_reg = {}         # (datum, region, segment) -> gefilterte Stellen
    hg_tag = {}          # (datum, hauptgruppe) -> gefilterte Stellen
    quelle_stand = Counter()          # Herkunft der Zuordnung am Stichtag
    hg_berufe = {}                    # hauptgruppe -> Counter(beruf) Stichtag
    for (d, rg, b), n in brb.items():
        if rg not in basis:
            continue
        e = einordnung(b)
        k = (d, rg, e.segment)
        seg_reg[k] = seg_reg.get(k, 0) + n
        hg_tag[(d, e.hauptgruppe)] = hg_tag.get((d, e.hauptgruppe), 0) + n
        if d == stand:
            quelle_stand[e.quelle] += n
            hg_berufe.setdefault(e.hauptgruppe, Counter())[b] += n
    seg_tag = {}         # (datum, segment) -> Summe ueber die Basisgebiete
    for (d, _rg, sg), n in seg_reg.items():
        seg_tag[(d, sg)] = seg_tag.get((d, sg), 0) + n
    ges_tag = {d: sum(v for (dd, _s), v in seg_tag.items() if dd == d)
               for d in daten}
    akt = lambda sg, d=stand: seg_tag.get((d, sg), 0)
    # Segmente nach aktueller Groesse, "Keine Angabe" (Code "") ans Ende
    segs = sorted(set(SEGMENTE) | {sg for (_d, sg) in seg_tag},
                  key=lambda sg: (sg == "", -akt(sg), sg))
    seg_name = lambda sg: SEGMENTE.get(sg, SONSTIGE)
    seg_kurz = lambda sg: SEGMENT_KURZ.get(sg, SONSTIGE)
    hgs = sorted(set(HAUPTGRUPPEN) | {hg for (_d, hg) in hg_tag},
                 key=lambda hg: (hg == "", -hg_tag.get((stand, hg), 0), hg))
    hg_name = lambda hg: (f"{hg} {HAUPTGRUPPEN[hg][0]}" if hg in HAUPTGRUPPEN
                          else SONSTIGE)

    def anteil(wert_tag, d, x):
        return wert_tag.get((d, x), 0) / ges_tag[d] if ges_tag.get(d) else None

    def pp(wert_tag, x, dx):
        """Veraenderung des Anteils in Prozentpunkten Stand vs. dx."""
        a, b = anteil(wert_tag, stand, x), anteil(wert_tag, dx, x) if dx else None
        return round((a - b) * 100, 2) if a is not None and b is not None else None

    # Karriereseiten-Stellen, die NICHT in den BA-Daten stehen, je Segment
    seg_code_von_name = {v: k for k, v in SEGMENTE.items()}
    nur_sj = Counter(seg_code_von_name.get(r["branche"], "")
                     for r in alle if r["offen"] == "ja"
                     and r["herkunft"] == HERKUNFT_SJ)

    # Engpass: Arbeitslose und gemeldete Stellen je Segment, BA-Statistik,
    # Agentur fuer Arbeit Waiblingen (= Rems-Murr-Kreis), letzter Monat
    bab = []
    bab_pfad = os.path.join(BASE, "data_historie", "ba_berufe.csv")
    if os.path.exists(bab_pfad):
        with open(bab_pfad, encoding="utf-8-sig", newline="") as fh:
            bab = list(csv.DictReader(fh, delimiter=";"))
    bab_monat = max((r["monat"] for r in bab), default=None)
    bab_wert = {(r["art"], r["segment"]): float(r["anzahl"] or 0)
                for r in bab if r["monat"] == bab_monat}

    def engpass(sg):
        alo = bab_wert.get(("Arbeitslose", seg_name(sg)))
        gst = bab_wert.get(("Gemeldete Arbeitsstellen", seg_name(sg)))
        return alo, gst, (round(alo / gst, 1) if alo is not None and gst else None)

    fmt = lambda d: f"{as_date(d):%d.%m.%Y}" if d else "n/a"
    zr30 = f"{fmt(d30)} – {fmt(stand)}"
    d0 = daten[0]                       # erster Erhebungstag
    zr0 = f"{fmt(d0)} – {fmt(stand)}"
    bab_txt = (f"{bab_monat[5:]}/{bab_monat[:4]}" if bab_monat else "n/a")

    bn = wb.create_sheet("Branchen")
    bn["A1"] = ("Branchenanalyse: offene Stellen nach Berufssegment (BA, KldB 2010), "
                + " + ".join(reg_name(r) for r in basis))
    bn["A1"].font = Font(name=ARIAL, bold=True, size=14)
    bn["A2"] = (f"Stand {fmt(stand)}. Einteilung nach der offiziellen "
                "Klassifikation der Berufe (KldB 2010) der Bundesagentur: "
                "37 Berufshauptgruppen → 14 Berufssegmente → 5 Sektoren, "
                "dieselbe Gliederung wie die BA-Arbeitsmarktstatistik. "
                "Nur geladene Stellen im 50-km-Radius, keine Hochrechnung. "
                "Alte Tage: first_seen/last_seen-Naeherung; neue Tage: Tagesbeobachtungen. "
                "Methodenwechsel und Abdeckung bei Trends beachten. "
                "Arbeitslosenzahlen der AA Waiblingen sind separate Vergleichsdaten, "
                "keine 50-km-Statistik. Zuordnung je Beruf: "
                "Blatt Branchen-Zuordnung.")

    # Kennzahlen-Kopf
    pp30 = {sg: pp(seg_tag, sg, d30) for sg in segs if sg}
    pp_ok = {k: v for k, v in pp30.items() if v is not None}
    pp0 = {sg: pp(seg_tag, sg, d0) for sg in segs if sg}
    pp0_ok = {k: v for k, v in pp0.items() if v is not None}
    gew0 = max(pp0_ok, key=pp0_ok.get) if pp0_ok else None
    ver0 = min(pp0_ok, key=pp0_ok.get) if pp0_ok else None
    gewinner = max(pp_ok, key=pp_ok.get) if pp_ok else None
    verlierer = min(pp_ok, key=pp_ok.get) if pp_ok else None
    n_q = sum(quelle_stand.values()) or 1
    kpis = [
        ("Offene Stellen (Basis)", round(ges_tag[stand]), "#,##0"),
        (f"Δ 30 Tage ({zr30})",
         round(ges_tag[stand] - ges_tag[d30]) if d30 else None,
         "+#,##0;-#,##0;0"),
        ("Stärkster Zuwachs (Anteil)",
         f"{seg_kurz(gewinner)}: {pp_ok[gewinner]:+.2f} Prozentpunkte"
         if gewinner else "n/a", None),
        ("Stärkster Rückgang (Anteil)",
         f"{seg_kurz(verlierer)}: {pp_ok[verlierer]:+.2f} Prozentpunkte"
         if verlierer else "n/a", None),
        (f"Δ seit Beginn ({zr0})",
         round(ges_tag[stand] - ges_tag[d0]), "+#,##0;-#,##0;0"),
        ("Seit Beginn: Zuwachs / Rückgang (Anteil)",
         (f"{seg_kurz(gew0)}: {pp0_ok[gew0]:+.2f} Pp. / "
          f"{seg_kurz(ver0)}: {pp0_ok[ver0]:+.2f} Pp.") if gew0 else "n/a",
         None),
        ("Zuordnung per KldB-Code / Stichwort",
         f"{(quelle_stand['KldB'] + quelle_stand['Hand']) / n_q:.0%} / "
         f"{quelle_stand['Stichwort'] / n_q:.0%} der Stellen "
         f"({quelle_stand['offen'] / n_q:.1%} ohne Zuordnung)", None),
    ]
    for i, (lab, wert, nf) in enumerate(kpis, start=4):
        bn.cell(row=i, column=1, value=lab).font = Font(name=ARIAL, bold=True)
        c = bn.cell(row=i, column=2, value=wert)
        c.font = Font(name=ARIAL, bold=True, size=12, color="1D3C6E")
        if nf:
            c.number_format = nf

    # ---- Tabelle A: Segmente
    z0 = 13
    bn.cell(row=z0 - 1, column=1, value="Berufssegmente").font = Font(
        name=ARIAL, bold=True, size=12)
    kopf = (["Berufssegment", "Stellen aktuell", "Anteil", "Δ 7 Tage",
             "Δ 7 Tage %", "Δ 30 Tage", "Δ 30 Tage %", f"Anteil am {fmt(d30)}",
             f"Δ Anteil in Prozentpunkten ({zr30})",
             f"Δ seit Beginn ({fmt(d0)})", f"Δ % seit Beginn ({fmt(d0)})",
             f"Anteil am {fmt(d0)}",
             f"Δ Anteil in Prozentpunkten seit Beginn ({zr0})"]
            + [reg_name(r) for r in basis]
            + ["Nur Karriereseite (ScrapJobs)", "Gesamt inkl. Karriereseite",
               "Anteil gesamt", f"Arbeitslose ({bab_txt}, AA Waiblingen)",
               f"Gemeldete Stellen BA-Statistik ({bab_txt})",
               "Arbeitslose je gemeldeter Stelle", "Sektor"])
    c_reg = 14
    c_sj = c_reg + len(basis)
    for c, t in enumerate(kopf, start=1):
        bn.cell(row=z0, column=c, value=t)
    style_header(bn, len(kopf), row=z0)
    bn.row_dimensions[z0].height = 70
    bn.freeze_panes = bn.cell(row=z0 + 1, column=2)
    sj_summe = sum(nur_sj.values())
    gesamt_alle = round(ges_tag[stand]) + sj_summe
    for i, sg in enumerate(segs, start=z0 + 1):
        a = round(akt(sg))
        bn.cell(row=i, column=1, value=seg_name(sg))
        bn.cell(row=i, column=2, value=a).number_format = "#,##0"
        bn.cell(row=i, column=3, value=anteil(seg_tag, stand, sg)
                ).number_format = "0.0%"
        for (dx, c_abs, c_pct) in ((d7, 4, 5), (d30, 6, 7)):
            if dx is None:
                continue
            alt = round(akt(sg, dx))
            bn.cell(row=i, column=c_abs, value=a - alt).number_format = \
                "+#,##0;-#,##0;0"
            if alt:
                bn.cell(row=i, column=c_pct, value=a / alt - 1
                        ).number_format = "+0.0%;-0.0%;0.0%"
        if d30 is not None:
            bn.cell(row=i, column=8, value=anteil(seg_tag, d30, sg)
                    ).number_format = "0.0%"
            bn.cell(row=i, column=9, value=pp(seg_tag, sg, d30)
                    ).number_format = "+0.00;-0.00;0.00"
        alt0 = round(akt(sg, d0))
        bn.cell(row=i, column=10, value=a - alt0).number_format = \
            "+#,##0;-#,##0;0"
        if alt0:
            bn.cell(row=i, column=11, value=a / alt0 - 1
                    ).number_format = "+0.0%;-0.0%;0.0%"
        bn.cell(row=i, column=12, value=anteil(seg_tag, d0, sg)
                ).number_format = "0.0%"
        bn.cell(row=i, column=13, value=pp(seg_tag, sg, d0)
                ).number_format = "+0.00;-0.00;0.00"
        for j, rg in enumerate(basis, start=c_reg):
            bn.cell(row=i, column=j, value=round(seg_reg.get((stand, rg, sg), 0))
                    ).number_format = "#,##0"
        n_sj = nur_sj.get(sg, 0)
        bn.cell(row=i, column=c_sj, value=n_sj).number_format = "#,##0"
        bn.cell(row=i, column=c_sj + 1, value=a + n_sj).number_format = "#,##0"
        if gesamt_alle:
            bn.cell(row=i, column=c_sj + 2, value=(a + n_sj) / gesamt_alle
                    ).number_format = "0.0%"
        alo, gst, quote = engpass(sg)
        bn.cell(row=i, column=c_sj + 3, value=alo).number_format = "#,##0"
        bn.cell(row=i, column=c_sj + 4, value=gst).number_format = "#,##0"
        bn.cell(row=i, column=c_sj + 5, value=quote).number_format = "0.0"
        bn.cell(row=i, column=c_sj + 6,
                value=SEKTOREN.get(sg[:2], "") if sg else "")
    z_sum = z0 + 1 + len(segs)
    bn.cell(row=z_sum, column=1, value="Summe").font = Font(name=ARIAL, bold=True)
    bn.cell(row=z_sum, column=2, value=round(ges_tag[stand])).number_format = "#,##0"
    for dx, c_abs in ((d7, 4), (d30, 6)):
        if dx is not None:
            bn.cell(row=z_sum, column=c_abs,
                    value=round(ges_tag[stand]) - round(ges_tag[dx])
                    ).number_format = "+#,##0;-#,##0;0"
    bn.cell(row=z_sum, column=10,
            value=round(ges_tag[stand]) - round(ges_tag[d0])
            ).number_format = "+#,##0;-#,##0;0"
    for j, rg in enumerate(basis, start=c_reg):
        bn.cell(row=z_sum, column=j, value=round(sum(
            seg_reg.get((stand, rg, sg), 0) for sg in segs))).number_format = "#,##0"
    bn.cell(row=z_sum, column=c_sj, value=sj_summe).number_format = "#,##0"
    bn.cell(row=z_sum, column=c_sj + 1, value=gesamt_alle).number_format = "#,##0"
    alo_g = bab_wert.get(("Arbeitslose", "Insgesamt"))
    gst_g = bab_wert.get(("Gemeldete Arbeitsstellen", "Insgesamt"))
    bn.cell(row=z_sum, column=c_sj + 3, value=alo_g).number_format = "#,##0"
    bn.cell(row=z_sum, column=c_sj + 4, value=gst_g).number_format = "#,##0"
    if alo_g and gst_g:
        bn.cell(row=z_sum, column=c_sj + 5, value=round(alo_g / gst_g, 1)
                ).number_format = "0.0"
    for c in range(1, len(kopf) + 1):
        bn.cell(row=z_sum, column=c).font = Font(name=ARIAL, bold=True)

    # bedingte Formatierung: Balken fuer Bestand, Ampel fuer Veraenderungen
    erste, letzte = z0 + 1, z_sum - 1
    bn.conditional_formatting.add(
        f"B{erste}:B{letzte}",
        DataBarRule(start_type="num", start_value=0, end_type="max",
                    color="5B8BD0"))
    ampel = dict(start_type="min", start_color="F8696B", mid_type="num",
                 mid_value=0, mid_color="FFFFFF", end_type="max",
                 end_color="63BE7B")
    for col in ("D", "F", "I", "J", "M"):
        bn.conditional_formatting.add(f"{col}{erste}:{col}{letzte}",
                                      ColorScaleRule(**ampel))
    col_q = get_column_letter(c_sj + 5)
    bn.conditional_formatting.add(
        f"{col_q}{erste}:{col_q}{letzte}",
        ColorScaleRule(start_type="min", start_color="F8696B",
                       mid_type="percentile", mid_value=50, mid_color="FFEB84",
                       end_type="max", end_color="63BE7B"))

    # ---- Tabelle: Sektoren
    zs0 = z_sum + 3
    bn.cell(row=zs0 - 1, column=1,
            value=(f"Berufssektoren (Veränderung {zr30} bzw. seit Beginn "
                   f"{zr0})")).font = Font(
        name=ARIAL, bold=True, size=12)
    kopf_s = ["Berufssektor", "Stellen aktuell", "Anteil", "Δ 30 Tage",
              "Δ Anteil 30 Tage (Pp.)", f"Δ seit {fmt(d0)}",
              f"Δ Anteil seit {fmt(d0)} (Pp.)"]
    for c, t in enumerate(kopf_s, start=1):
        bn.cell(row=zs0, column=c, value=t)
    style_header(bn, len(kopf_s), row=zs0)
    sek_tag = {}
    for (d, sg), v in seg_tag.items():
        sek_tag[(d, sg[:2])] = sek_tag.get((d, sg[:2]), 0) + v
    for i, sk in enumerate(list(SEKTOREN) + [""], start=zs0 + 1):
        a = round(sek_tag.get((stand, sk), 0))
        bn.cell(row=i, column=1, value=f"{sk} {SEKTOREN[sk]}" if sk else SONSTIGE)
        bn.cell(row=i, column=2, value=a).number_format = "#,##0"
        bn.cell(row=i, column=3, value=anteil(sek_tag, stand, sk)
                ).number_format = "0.0%"
        if d30:
            bn.cell(row=i, column=4, value=a - round(sek_tag.get((d30, sk), 0))
                    ).number_format = "+#,##0;-#,##0;0"
            bn.cell(row=i, column=5, value=pp(sek_tag, sk, d30)
                    ).number_format = "+0.00;-0.00;0.00"
        bn.cell(row=i, column=6, value=a - round(sek_tag.get((d0, sk), 0))
                ).number_format = "+#,##0;-#,##0;0"
        bn.cell(row=i, column=7, value=pp(sek_tag, sk, d0)
                ).number_format = "+0.00;-0.00;0.00"

    # ---- Tabelle B: Berufshauptgruppen
    zh0 = zs0 + len(SEKTOREN) + 4
    bn.cell(row=zh0 - 1, column=1,
            value=("Berufshauptgruppen (Unterebene, 2-Steller KldB 2010; "
                   f"Veränderung {zr30} bzw. seit Beginn {zr0})")
            ).font = Font(name=ARIAL, bold=True, size=12)
    kopf_h = ["Berufshauptgruppe", "Stellen aktuell", "Anteil", "Δ 30 Tage",
              "Δ 30 Tage %", "Δ Anteil (Pp.)", f"Stellen am {fmt(d30)}",
              f"Anteil am {fmt(d30)}", f"Δ seit {fmt(d0)}",
              f"Δ % seit {fmt(d0)}", f"Δ Anteil seit {fmt(d0)} (Pp.)",
              "Berufssegment", "Häufigste Berufe (Stellen)"]
    for c, t in enumerate(kopf_h, start=1):
        bn.cell(row=zh0, column=c, value=t)
    style_header(bn, len(kopf_h), row=zh0)
    for i, hg in enumerate(hgs, start=zh0 + 1):
        a = round(hg_tag.get((stand, hg), 0))
        bn.cell(row=i, column=1, value=hg_name(hg))
        bn.cell(row=i, column=2, value=a).number_format = "#,##0"
        bn.cell(row=i, column=3, value=anteil(hg_tag, stand, hg)
                ).number_format = "0.0%"
        if d30:
            alt = round(hg_tag.get((d30, hg), 0))
            bn.cell(row=i, column=4, value=a - alt).number_format = \
                "+#,##0;-#,##0;0"
            if alt:
                bn.cell(row=i, column=5, value=a / alt - 1
                        ).number_format = "+0.0%;-0.0%;0.0%"
            bn.cell(row=i, column=6, value=pp(hg_tag, hg, d30)
                    ).number_format = "+0.00;-0.00;0.00"
            bn.cell(row=i, column=7, value=alt).number_format = "#,##0"
            bn.cell(row=i, column=8, value=anteil(hg_tag, d30, hg)
                    ).number_format = "0.0%"
        alt0 = round(hg_tag.get((d0, hg), 0))
        bn.cell(row=i, column=9, value=a - alt0).number_format = \
            "+#,##0;-#,##0;0"
        if alt0:
            bn.cell(row=i, column=10, value=a / alt0 - 1
                    ).number_format = "+0.0%;-0.0%;0.0%"
        bn.cell(row=i, column=11, value=pp(hg_tag, hg, d0)
                ).number_format = "+0.00;-0.00;0.00"
        sg = HAUPTGRUPPEN[hg][1] if hg in HAUPTGRUPPEN else ""
        bn.cell(row=i, column=12, value=seg_kurz(sg))
        top = hg_berufe.get(hg, Counter()).most_common(3)
        bn.cell(row=i, column=13, value="; ".join(f"{b} ({n})" for b, n in top))
    zh_end = zh0 + len(hgs)
    bn.conditional_formatting.add(
        f"B{zh0 + 1}:B{zh_end}",
        DataBarRule(start_type="num", start_value=0, end_type="max",
                    color="5B8BD0"))
    for col in ("D", "F", "I", "K"):
        bn.conditional_formatting.add(f"{col}{zh0 + 1}:{col}{zh_end}",
                                      ColorScaleRule(**ampel))

    # ---- Diagrammdaten (sortiert je Diagramm), unterhalb der Tabellen
    zd = zh_end + 4
    bn.cell(row=zd - 1, column=1, value=(
        "Diagrammdaten (automatisch erzeugt, sortiert je Diagramm)")
            ).font = Font(name=ARIAL, bold=True, italic=True, color="808080")
    segs_d = [sg for sg in segs if sg]
    blk = {}

    def block(spalte, titel, kopfzeile, zeilen, formate):
        for j, t in enumerate(kopfzeile):
            bn.cell(row=zd, column=spalte + j, value=t)
        for c in range(spalte, spalte + len(kopfzeile)):
            bn.cell(row=zd, column=c).font = Font(name=ARIAL, bold=True)
        for i, werte in enumerate(zeilen, start=zd + 1):
            for j, v in enumerate(werte):
                cell = bn.cell(row=i, column=spalte + j, value=v)
                if formate[j]:
                    cell.number_format = formate[j]
        blk[titel] = (spalte, len(zeilen))

    block(1, "ranking", ["Segment", "BA (hochgerechnet)", "Nur Karriereseite"],
          [(seg_kurz(sg), round(akt(sg)), nur_sj.get(sg, 0)) for sg in segs_d],
          [None, "#,##0", "#,##0"])
    pp_sort = sorted((sg for sg in segs_d if pp30.get(sg) is not None),
                     key=lambda sg: -pp30[sg])
    block(5, "pp", ["Segment", f"Δ Prozentpunkte ({zr30})"],
          [(seg_kurz(sg), pp30[sg]) for sg in pp_sort], [None, "+0.00;-0.00"])
    pp0_sort = sorted((sg for sg in segs_d if pp0.get(sg) is not None),
                      key=lambda sg: -pp0[sg])
    block(14, "pp0", ["Segment", f"Δ Prozentpunkte seit Beginn ({zr0})"],
          [(seg_kurz(sg), pp0[sg]) for sg in pp0_sort], [None, "+0.00;-0.00"])
    eng = sorted(((sg, engpass(sg)[2]) for sg in segs_d
                  if engpass(sg)[2] is not None), key=lambda t: -t[1])
    block(8, "engpass", ["Segment", "Arbeitslose je gemeldeter Stelle"],
          [(seg_kurz(sg), q) for sg, q in eng], [None, "0.0"])
    hg_top = [hg for hg in hgs if hg][:15]
    block(11, "hg", ["Berufshauptgruppe", "Stellen aktuell"],
          [((hg_name(hg)[:45] + "…") if len(hg_name(hg)) > 46 else hg_name(hg),
            round(hg_tag.get((stand, hg), 0))) for hg in hg_top],
          [None, "#,##0"])

    def ref(titel, spalte_off, mit_kopf=True):
        sp, n = blk[titel]
        return Reference(bn, min_col=sp + spalte_off,
                         min_row=zd if mit_kopf else zd + 1, max_row=zd + n)

    # ---- Diagramme rechts neben den Tabellen
    anker_spalte = get_column_letter(len(kopf) + 2)
    zeile_anker = 3

    def setze(ch, hoehe_zeilen):
        nonlocal zeile_anker
        bn.add_chart(ch, f"{anker_spalte}{zeile_anker}")
        zeile_anker += hoehe_zeilen

    n_seg = blk["ranking"][1]
    c1 = balken_chart("1  Offene Stellen je Berufssegment (BA + nur Karriereseite)",
                      "Stellen", n_seg, hoehe=11, breite=20)
    c1.grouping = "stacked"
    c1.overlap = 100
    c1.add_data(ref("ranking", 1), titles_from_data=True)
    c1.add_data(ref("ranking", 2), titles_from_data=True)
    c1.set_categories(ref("ranking", 0, False))
    setze(c1, 23)

    if blk["pp"][1]:
        c2 = balken_chart(f"2  Gewinner und Verlierer: Δ Anteil in Prozentpunkten "
                          f"({zr30})", "Prozentpunkte", blk["pp"][1],
                          hoehe=11, breite=20)
        c2.add_data(ref("pp", 1), titles_from_data=True)
        c2.set_categories(ref("pp", 0, False))
        c2.legend = None
        c2.y_axis.number_format = "+0.0;-0.0;0"
        # Beschriftung links aussen statt an der Nulllinie (sonst liegen die
        # Namen auf den negativen Balken)
        c2.x_axis.tickLblPos = "low"
        ser = c2.series[0]
        ser.invertIfNegative = False
        ser.graphicalProperties.solidFill = "63BE7B"
        # negative Balken rot: je Datenpunkt einfaerben
        for idx, sg in enumerate(pp_sort):
            if pp30[sg] < 0:
                dp = DataPoint(idx=idx)
                dp.graphicalProperties.solidFill = "F8696B"
                ser.dPt.append(dp)
        setze(c2, 23)

    if blk["pp0"][1]:
        c2b = balken_chart(f"2b  Gewinner und Verlierer seit Beginn: Δ Anteil "
                           f"in Prozentpunkten ({zr0})", "Prozentpunkte",
                           blk["pp0"][1], hoehe=11, breite=20)
        c2b.add_data(ref("pp0", 1), titles_from_data=True)
        c2b.set_categories(ref("pp0", 0, False))
        c2b.legend = None
        c2b.y_axis.number_format = "+0.0;-0.0;0"
        c2b.x_axis.tickLblPos = "low"
        ser = c2b.series[0]
        ser.invertIfNegative = False
        ser.graphicalProperties.solidFill = "63BE7B"
        for idx, sg in enumerate(pp0_sort):
            if pp0[sg] < 0:
                dp = DataPoint(idx=idx)
                dp.graphicalProperties.solidFill = "F8696B"
                ser.dPt.append(dp)
        setze(c2b, 23)

    if blk["engpass"][1]:
        c4 = balken_chart(f"3  Engpass: Arbeitslose je gemeldeter Stelle "
                          f"({bab_txt}, Rems-Murr) – niedrig = Fachkräfte knapp",
                          "Arbeitslose je Stelle", blk["engpass"][1],
                          hoehe=11, breite=20)
        c4.add_data(ref("engpass", 1), titles_from_data=True)
        c4.set_categories(ref("engpass", 0, False))
        c4.legend = None
        c4.y_axis.number_format = "0.0"
        setze(c4, 23)

    c6 = balken_chart("4  Top 15 Berufshauptgruppen (aktuell)", "Stellen",
                      blk["hg"][1], hoehe=12, breite=20)
    c6.add_data(ref("hg", 1), titles_from_data=True)
    c6.set_categories(ref("hg", 0, False))
    c6.legend = None
    setze(c6, 25)

    # ---- Branchen-Zeitreihe: Segmente, Anteile, Index, Hauptgruppen
    bt = wb.create_sheet("Branchen-Zeitreihe")
    kopf_t = (["Datum"] + [seg_kurz(sg) for sg in segs] + ["Summe"]
              + [f"Anteil {seg_kurz(sg)}" for sg in segs])
    top6 = segs_d[:6]
    basis_idx = d0                      # Index: erster Erhebungstag = 100
    kopf_t += [f"Index {seg_kurz(sg)}" for sg in top6]
    kopf_t += [hg_name(hg) for hg in hgs]
    bt.append(kopf_t)
    n_s = len(segs)
    c_anteil = n_s + 3
    c_index = c_anteil + n_s
    c_hg = c_index + len(top6)
    for i, d in enumerate(daten, start=2):
        bt.cell(row=i, column=1, value=as_date(d)).number_format = DATUM_FMT
        for j, sg in enumerate(segs, start=2):
            bt.cell(row=i, column=j, value=round(akt(sg, d))).number_format = "#,##0"
        bt.cell(row=i, column=n_s + 2, value=round(ges_tag[d])).number_format = "#,##0"
        for j, sg in enumerate(segs, start=c_anteil):
            bt.cell(row=i, column=j, value=anteil(seg_tag, d, sg)
                    ).number_format = "0.0%"
        for j, sg in enumerate(top6, start=c_index):
            b0 = akt(sg, basis_idx)
            bt.cell(row=i, column=j,
                    value=round(akt(sg, d) / b0 * 100, 1) if b0 else None
                    ).number_format = "0.0"
        for j, hg in enumerate(hgs, start=c_hg):
            bt.cell(row=i, column=j, value=round(hg_tag.get((d, hg), 0))
                    ).number_format = "#,##0"
    style_header(bt, len(kopf_t))
    bt.row_dimensions[1].height = 60
    n_d = len(daten)

    # 5: Anteile im Zeitverlauf (100-%-gestapelte Flaeche, 2D)
    c3 = AreaChart()
    c3.grouping = "percentStacked"
    c3.title = "5  Branchenmix im Zeitverlauf (Anteile der Segmente)"
    c3.height, c3.width = 12, 20
    _achsen_sichtbar(c3, None, "Anteil", "DD.MM.", "0%")
    c3.x_axis.tickLblSkip = c3.x_axis.tickMarkSkip = max(1, n_d // 12)
    c3.add_data(Reference(bt, min_col=2, max_col=n_s + 1, min_row=1,
                          max_row=n_d + 1), titles_from_data=True)
    c3.set_categories(Reference(bt, min_col=1, min_row=2, max_row=n_d + 1))
    c3.legend.position = "r"
    setze(c3, 25)

    # 6: Index der 6 groessten Segmente
    c5 = linien_chart(f"6  Entwicklung der 6 größten Segmente "
                      f"(Index, {fmt(basis_idx)} = 100)", None, "Index",
                      "DD.MM.", n_d, hoehe=11, breite=20)
    c5.y_axis.number_format = "0"
    idx_werte = [akt(sg, d) / akt(sg, basis_idx) * 100 for sg in top6
                 for d in daten if akt(sg, basis_idx)]
    if idx_werte:
        c5.y_axis.scaling.min = max(0, (int(min(idx_werte)) // 10) * 10)
        c5.y_axis.scaling.max = (int(max(idx_werte)) // 10 + 1) * 10
    c5.add_data(Reference(bt, min_col=c_index, max_col=c_index + len(top6) - 1,
                          min_row=1, max_row=n_d + 1), titles_from_data=True)
    c5.set_categories(Reference(bt, min_col=1, min_row=2, max_row=n_d + 1))
    setze(c5, 23)

    # absolute Zeitreihe weiterhin auf dem Zeitreihen-Blatt
    lc = linien_chart("Offene Stellen je Berufssegment", "Datum", "Stellen",
                      "DD.MM.", n_d, hoehe=13)
    lc.add_data(Reference(bt, min_col=2, max_col=n_s + 1, min_row=1,
                          max_row=n_d + 1), titles_from_data=True)
    lc.set_categories(Reference(bt, min_col=1, min_row=2, max_row=n_d + 1))
    bt.add_chart(lc, f"A{n_d + 4}")

    # ---- Branchen-Zuordnung: Transparenz je Beruf (filterbar)
    bzu = wb.create_sheet("Branchen-Zuordnung")
    bzu.append(["Beruf", "KldB-Code", "Berufshauptgruppe", "Berufssegment",
                "Berufssektor", "Zuordnung über", "Stellen aktuell (alle Gebiete)"])
    for i, b in enumerate(top_akt, start=2):
        e = einordnung(b)
        werte = [b, e.kldb or None, hg_name(e.hauptgruppe) if e.hauptgruppe
                 else SONSTIGE, e.segment_name,
                 SEKTOREN.get(e.sektor, SONSTIGE), e.quelle,
                 bges.get((stand, b), 0)]
        for j, v in enumerate(werte, start=1):
            bzu.cell(row=i, column=j, value=v)
    style_header(bzu, 7)
    bzu.auto_filter.ref = f"A1:G{len(top_akt) + 1}"
    hin = len(top_akt) + 3
    bzu.cell(row=hin, column=1, value=(
        "Zuordnung über: KldB = Code aus BERUFENET (tools/kldb_zuordnung.py, "
        "data/beruf_kldb.csv); Hand = Korrektur aus data/beruf_kldb_manuell.csv "
        "(Spalten beruf,kldb – hat Vorrang); Stichwort = Rückfall über "
        "Schlüsselwörter (branchen.py), bis BERUFENET den Beruf geliefert hat; "
        "offen = keine Zuordnung (Keine Angabe)."))

    zs["A12"] = "Branchenzuordnung"
    zs["B12"] = (f"{(quelle_stand['KldB'] + quelle_stand['Hand']) / n_q:.0%} "
                 f"der Stellen per KldB-Code, "
                 f"{quelle_stand['Stichwort'] / n_q:.0%} per Stichwort, "
                 f"{quelle_stand['offen'] / n_q:.1%} ohne Zuordnung "
                 "(Blätter Branchen, Branchen-Zuordnung)")
    zs["A12"].font = Font(name=ARIAL, bold=True)

    # ---------------- Aktuell (alle Berufe des Stichtags)
    ak = wb.create_sheet("Aktuell")
    kopf = (["Beruf"] + [reg_name(r) for r in regionen] +
            ["Gesamt", f"Vor 7 Tagen ({d7 or 'n/a'})",
             f"Vor 30 Tagen ({d30 or 'n/a'})", "Δ 7 Tage", "Δ 30 Tage",
             f"Erster Erhebungstag ({d0})", "Δ seit Beginn"])
    ak.append(kopf)
    nr = len(regionen)
    for i, b in enumerate(top_akt, start=2):
        ak.cell(row=i, column=1, value=b)
        for j, r in enumerate(regionen, start=2):
            ak.cell(row=i, column=j, value=brb.get((stand, r, b)))
        ges = bges.get((stand, b), 0)
        v7 = bges.get((d7, b)) if d7 else None
        v30 = bges.get((d30, b)) if d30 else None
        ak.cell(row=i, column=nr + 2, value=ges)
        ak.cell(row=i, column=nr + 3, value=v7)
        ak.cell(row=i, column=nr + 4, value=v30)
        ak.cell(row=i, column=nr + 5,
                value=(ges - v7) if v7 is not None else None)
        ak.cell(row=i, column=nr + 6,
                value=(ges - v30) if v30 is not None else None)
        v0 = bges.get((d0, b))
        ak.cell(row=i, column=nr + 7, value=v0)
        ak.cell(row=i, column=nr + 8,
                value=(ges - v0) if v0 is not None else None)
    style_header(ak, nr + 8)
    n_chart = min(15, len(top_akt))
    fl = balken_chart(f"Top {n_chart} Berufe nach Suchgebiet (aktuell)",
                      "Stellen", n_chart, hoehe=18, breite=24)
    # nur aktive Suchgebiete als Serien (eingestellte Spalten sind leer)
    fl.add_data(Reference(ak, min_col=2, max_col=n_akt + 1,
                          min_row=1, max_row=n_chart + 1),
                titles_from_data=True)
    fl.set_categories(Reference(ak, min_col=1, min_row=2,
                                max_row=n_chart + 1))
    ak.add_chart(fl, f"A{len(top_akt) + 4}")

    # ---------------- Log (Rohdaten)
    lg = wb.create_sheet("Log")
    lg.append(["Refnr", "Region", "Beruf", "Arbeitgeber",
               "Erstmals gesehen", "Zuletzt gesehen", "Standzeit (Tage)"])
    for i, r in enumerate(log, start=2):
        lg.cell(row=i, column=1, value=r["refnr"])
        lg.cell(row=i, column=2, value=reg_name(r["region"]))
        lg.cell(row=i, column=3, value=r["beruf"])
        lg.cell(row=i, column=4, value=r["arbeitgeber"])
        lg.cell(row=i, column=5, value=as_date(r["first_seen"])).number_format = DATUM_FMT
        lg.cell(row=i, column=6, value=as_date(r["last_seen"])).number_format = DATUM_FMT
        lg.cell(row=i, column=7, value=standzeit_tage(r))
    style_header(lg, 7)

    # ---------------- Standzeit je Beruf (ALLE Berufe im Log,
    #                  sortiert nach Zahl der Log-Eintraege)
    # Fest berechnet statt COUNTIFS: bei unbegrenzter Berufsliste und
    # grossem Log wuerde Excel sonst bei jedem Oeffnen lange rechnen,
    # und in Vorschau-Apps blieben Formelzellen leer.
    beruf_stat = {}
    for r in log:
        s = beruf_stat.setdefault(r["beruf"],
                                  {"log": 0, "offen": 0, "dauern": []})
        s["log"] += 1
        if ba_ist_offen(r, stand):
            s["offen"] += 1
        else:
            s["dauern"].append(standzeit_tage(r))
    st = wb.create_sheet("Standzeit")
    st.append(["Beruf", "Stellen im Log", "Aktuell offen", "Beendet",
               "Ø Standzeit beendeter Stellen (Tage)"])
    st_berufe = sorted(beruf_stat, key=lambda b: -beruf_stat[b]["log"])
    for i, b in enumerate(st_berufe, start=2):
        s = beruf_stat[b]
        st.cell(row=i, column=1, value=b)
        st.cell(row=i, column=2, value=s["log"])
        st.cell(row=i, column=3, value=s["offen"])
        st.cell(row=i, column=4, value=len(s["dauern"]))
        if s["dauern"]:
            st.cell(row=i, column=5,
                    value=round(statistics.mean(s["dauern"]), 1)
                    ).number_format = "0.0"
    style_header(st, 5)

    # ---------------- Arbeitgeber (alle mit aktuell offenen Stellen)
    ag_stat = {}
    for r in log:
        s = ag_stat.setdefault(r["arbeitgeber"],
                               {"log": 0, "offen": 0, "dauern": []})
        s["log"] += 1
        if ba_ist_offen(r, stand):
            s["offen"] += 1
        else:
            s["dauern"].append(standzeit_tage(r))
    ag = wb.create_sheet("Arbeitgeber")
    ag.append(["Arbeitgeber", "Offene Stellen (aktuell)",
               "Stellen im Log gesamt", "Beendet",
               "Ø Standzeit beendeter Stellen (Tage)"])
    offene_ag = sorted((a for a, s in ag_stat.items() if s["offen"]),
                       key=lambda a: -ag_stat[a]["offen"])
    for i, a in enumerate(offene_ag, start=2):
        s = ag_stat[a]
        ag.cell(row=i, column=1, value=a)
        ag.cell(row=i, column=2, value=s["offen"])
        ag.cell(row=i, column=3, value=s["log"])
        ag.cell(row=i, column=4, value=len(s["dauern"]))
        if s["dauern"]:
            ag.cell(row=i, column=5,
                    value=round(statistics.mean(s["dauern"]), 1)
                    ).number_format = "0.0"
    style_header(ag, 5)

    # ---------------- Arbeitgeber-Tempo: wer besetzt am schnellsten?
    # Rangliste nach kuerzester mittlerer Standzeit beendeter Stellen.
    # Kurze Standzeit heisst nur "Anzeige schnell wieder offline" --
    # meist Besetzung, es kann aber auch Loeschung oder Ablauf sein.
    tempo = [(a, s) for a, s in ag_stat.items()
             if len(s["dauern"]) >= AG_TEMPO_MIN_BEENDET]
    tempo.sort(key=lambda t: (statistics.mean(t[1]["dauern"]),
                              -len(t[1]["dauern"])))
    tp = wb.create_sheet("Arbeitgeber-Tempo")
    tp.append(["Arbeitgeber", "Ø Standzeit (Tage)", "Median (Tage)",
               "Beendete Stellen", "Aktuell offen", "Stellen im Log",
               "Anteil beendet"])
    for i, (a, s) in enumerate(tempo, start=2):
        tp.cell(row=i, column=1, value=a)
        tp.cell(row=i, column=2,
                value=round(statistics.mean(s["dauern"]), 1)
                ).number_format = "0.0"
        tp.cell(row=i, column=3,
                value=round(statistics.median(s["dauern"]), 1)
                ).number_format = "0.0"
        tp.cell(row=i, column=4, value=len(s["dauern"]))
        tp.cell(row=i, column=5, value=s["offen"])
        tp.cell(row=i, column=6, value=s["log"])
        tp.cell(row=i, column=7,
                value=len(s["dauern"]) / s["log"]).number_format = "0%"
    style_header(tp, 7)
    hin = len(tempo) + 3
    tp.cell(row=hin, column=1, value=(
        f"Nur Arbeitgeber mit mindestens {AG_TEMPO_MIN_BEENDET} beendeten "
        "Stellen (Rauschen von Einzelfaellen). 'Anteil beendet' zeigt den "
        "Umschlag: hoch = es wird laufend besetzt und nachgelegt. Achtung "
        "bei der Deutung: Zeitarbeitsfirmen schalten viele kurzlaufende "
        "Anzeigen und stehen deshalb oft vorn; kurze Standzeit kann auch "
        "Loeschung oder Ablauf der Anzeige statt Besetzung sein."))
    if tempo:
        n_bar = min(20, len(tempo))
        bc = balken_chart(
            f"Schnellste Arbeitgeber: Ø Standzeit in Tagen "
            f"(min. {AG_TEMPO_MIN_BEENDET} beendete Stellen)",
            "Ø Tage", n_bar, breite=24)
        bc.add_data(Reference(tp, min_col=2, min_row=1, max_row=n_bar + 1),
                    titles_from_data=True)
        bc.set_categories(Reference(tp, min_col=1, min_row=2,
                                    max_row=n_bar + 1))
        bc.legend = None   # eine Serie, Legende ueberfluessig
        tp.add_chart(bc, f"A{hin + 2}")

    # ---------------- Arbeitslose (Kreisebene, Regionaldatenbank/GENESIS)
    al_daten = lade_arbeitslose()
    monate = sorted({(r["jahr"], r["monat"]) for r in al_daten})
    alm = {(r["jahr"], r["monat"], r["ags"]): r for r in al_daten}
    ags_liste = list(AL_KREISE)
    if al_daten:
        ab = wb.create_sheet("Arbeitslose")
        ab.append(["Monat"]
                  + [f"{AL_KREISE[a]} Arbeitslose" for a in ags_liste]
                  + [f"{AL_KREISE[a]} Quote %" for a in ags_liste])
        for i, (j, m) in enumerate(monate, start=2):
            ab.cell(row=i, column=1,
                    value=date(j, m, 1)).number_format = "MM.YYYY"
            for k, a in enumerate(ags_liste):
                r = alm.get((j, m, a), {})
                ab.cell(row=i, column=2 + k,
                        value=r.get("arbeitslose")).number_format = "#,##0"
                q = ab.cell(row=i, column=2 + len(ags_liste) + k,
                            value=r.get("quote"))
                q.number_format = "0.0"
        style_header(ab, 1 + 2 * len(ags_liste))
        nz = len(monate) + 1
        abc = linien_chart("Arbeitslose je Kreis (Monatswerte)",
                           "Monat", "Arbeitslose", "MM.YY", len(monate))
        abc.add_data(Reference(ab, min_col=2, max_col=1 + len(ags_liste),
                               min_row=1, max_row=nz),
                     titles_from_data=True)
        abc.set_categories(Reference(ab, min_col=1, min_row=2, max_row=nz))
        ab.add_chart(abc, f"A{nz + 3}")

    # ---------------- AL-Relation (Berufe manuell, Kreise automatisch)
    al = wb.create_sheet("AL-Relation")
    al.append(["Beruf", "Offene Stellen (aktuell)",
               "Arbeitslose (manuell, BA-Statistik)",
               "Arbeitslose je Stelle"])
    for i, b in enumerate(al_berufe, start=2):
        al.cell(row=i, column=1, value=b)
        # fester Wert statt Verweis auf Aktuell: so ist die Spalte auch
        # in Vorschau-Apps und auf dem Handy gefuellt
        al.cell(row=i, column=2, value=bges.get((stand, b), 0))
        c_in = al.cell(row=i, column=3)
        c_in.font = INPUT_FONT
        al.cell(row=i, column=4,
                value=f'=IF(OR(C{i}="",B{i}=0),"",ROUND(C{i}/B{i},1))')
        al.cell(row=i, column=4).number_format = "0.0"
    style_header(al, 4)

    start = len(al_berufe) + 4
    if al_daten:
        # Kreisblock unter der Berufstabelle: Arbeitslose (letzter Monat
        # aus GENESIS) je offener Stelle des passenden Suchgebiets
        j_l, m_l = monate[-1]
        al.cell(row=start, column=1,
                value=f"Kreisebene (Arbeitslose Stand {m_l:02d}/{j_l}, "
                      "Regionaldatenbank)")
        al.cell(row=start, column=1).font = Font(name=ARIAL, bold=True)
        for c, t in enumerate(["Kreis", "Arbeitslose",
                               "Offene Stellen (Suchgebiet)",
                               "Arbeitslose je Stelle"], start=1):
            al.cell(row=start + 1, column=c, value=t)
        style_header(al, 4, row=start + 1)
        zeile = start + 2
        # Teil-/Ueberlappungsgebiete hier auslassen: Waiblingen 30 km und
        # Backnang 10 km liegen im Rems-Murr-Kreis, Stuttgart Ost
        # (Fellbach 8 km) deckt den Stadtkreis nur minimal ab
        auslassen = {"waiblingen_30km", "backnang_10km", "stuttgart_ost"}
        for reg, ags in REGION_ZU_AGS.items():
            if reg not in aktiv or reg in auslassen or ags not in AL_KREISE:
                continue
            alo = alm.get((j_l, m_l, ags), {}).get("arbeitslose")
            stellen = snap_map.get((stand, reg))
            al.cell(row=zeile, column=1, value=AL_KREISE[ags])
            al.cell(row=zeile, column=2, value=alo).number_format = "#,##0"
            al.cell(row=zeile, column=3, value=stellen).number_format = "#,##0"
            if alo and stellen:
                al.cell(row=zeile, column=4,
                        value=round(alo / stellen, 1)).number_format = "0.0"
            zeile += 1
        al.cell(row=zeile + 1, column=1,
                value=("Hinweis: Suchgebiete sind Umkreissuchen und decken "
                       "die Kreise nur naeherungsweise ab. Arbeitslose je "
                       "Beruf gibt es nicht in der Regionaldatenbank, "
                       "die blaue Spalte oben bleibt daher manuell."))
    else:
        al.cell(row=start, column=1, value=(
            "Kreisdaten fehlen: data/arbeitslose.csv ist (noch) leer. "
            "GENESIS_USER/GENESIS_PASS (oder GENESIS_TOKEN) als GitHub-Secrets setzen "
            "(kostenloses Konto auf regionalstatistik.de), dann fuellen "
            "sich das Blatt Arbeitslose und dieser Block automatisch."))


    # ---------------- Alle Quellen gemeinsam (BA + Karriereseiten)
    # Die BA-Blaetter oben bleiben reine BA-Zahlen (Zeitreihen bleiben
    # vergleichbar). Hier: gemeinsames Format, jede Stelle einmal.
    alle_offen = [r for r in alle if r["offen"] == "ja"]
    herk = [HERKUNFT_BA, HERKUNFT_BEIDE, HERKUNFT_SJ]

    gs = wb.create_sheet("Gesamt-Übersicht")
    gs["A1"] = "Offene Stellen: 50 km Luftlinie um Waiblingen (jede Stelle einmal gezählt)"
    gs["A1"].font = Font(name=ARIAL, bold=True, size=12)
    zeile_nr = 3

    def kreuz(titel, schluessel, limit=None):
        nonlocal zeile_nr
        zaehl = {}
        for r in alle_offen:
            z = zaehl.setdefault(r[schluessel], Counter())
            z[r["herkunft"]] += 1
        reihen = sorted(zaehl, key=lambda x: -sum(zaehl[x].values()))
        if limit:
            reihen = reihen[:limit]
        kopf = [titel, "Gesamt", "nur BA", "BA + Karriereseite",
                "nur Karriereseite", "Anteil nur Karriereseite"]
        for j, v in enumerate(kopf, start=1):
            gs.cell(row=zeile_nr, column=j, value=v)
        style_header(gs, len(kopf), row=zeile_nr)
        for x in reihen:
            zeile_nr += 1
            z = zaehl[x]
            ges = sum(z.values())
            werte = [x, ges] + [z[h] for h in herk] + [z[HERKUNFT_SJ] / ges]
            for j, v in enumerate(werte, start=1):
                gs.cell(row=zeile_nr, column=j, value=v)
            gs.cell(row=zeile_nr, column=6).number_format = "0%"
        zeile_nr += 3

    kreuz("Kreis", "kreis")
    kreuz("Berufssegment", "branche")
    for r in alle_offen:
        r["hg_name"] = (f"{r['hauptgruppe']} {HAUPTGRUPPEN[r['hauptgruppe']][0]}"
                        if r.get("hauptgruppe") in HAUPTGRUPPEN else SONSTIGE)
    kreuz("Berufshauptgruppe", "hg_name")
    kreuz("Arbeitgeber (Top 50)", "arbeitgeber", limit=50)
    gs.cell(row=zeile_nr, column=1, value=(
        "Kreis: aus dem Arbeitsort (orte.py), überschneidungsfrei - anders "
        "als die BA-Suchgebiete. Berufssegment/-hauptgruppe (KldB 2010, "
        "siehe Blatt Branchen): aus dem BA-Beruf; bei reinen "
        "Karriereseiten-Stellen über gleichen Titel in den BA-Daten, "
        "Stichwörter im Titel oder die übliche Branche des Arbeitgebers "
        "(Spalte branche_quelle im Blatt Alle Stellen)."))

    # Blatt nur mit offenen Stellen (sonst wird die Excel ~3x so gross);
    # der komplette Bestand inkl. beendeter Stellen steht in
    # data/stellen_alle.csv
    al_ws = wb.create_sheet("Alle Stellen")
    kopf_alle = ["Herkunft", "Arbeitgeber", "Stelle", "Ort", "Kreis",
                 "BA-Suchgebiet", "Beruf", "Beruf-Quelle", "Branche",
                 "Branche-Quelle", "Erstmals gesehen", "Zuletzt gesehen",
                 "Offen", "Standzeit bisher (Tage)", "Link", "Stellen-ID"]
    al_ws.append(kopf_alle)
    for i, r in enumerate(sorted(
            alle_offen, key=lambda r: (r["arbeitgeber"], r["titel"])),
            start=2):
        url = r["url"] or (
            "https://www.arbeitsagentur.de/jobsuche/jobdetail/" + r["ba_refnr"])
        werte = [r["herkunft"], r["arbeitgeber"], r["titel"], r["ort"],
                 r["kreis"], reg_name(r["ba_suchgebiet"]) if r["ba_suchgebiet"]
                 else None, r["beruf"] or None, r["beruf_quelle"],
                 r["branche"], r["branche_quelle"], as_date(r["first_seen"]),
                 as_date(r["last_seen"]), r["offen"], r["standzeit_tage"],
                 url, r["stellen_id"]]
        for j, v in enumerate(werte, start=1):
            al_ws.cell(row=i, column=j, value=v)
        al_ws.cell(row=i, column=11).number_format = DATUM_FMT
        al_ws.cell(row=i, column=12).number_format = DATUM_FMT
    style_header(al_ws, len(kopf_alle))
    al_ws.auto_filter.ref = f"A1:{get_column_letter(len(kopf_alle))}{len(alle_offen) + 1}"
    al_ws.freeze_panes = "A2"

    n_her = Counter(r["herkunft"] for r in alle_offen)
    zs["A11"] = "Alle Quellen (offen)"
    zs["B11"] = (f"{len(alle_offen)} Stellen: {n_her[HERKUNFT_BA]} nur BA, "
                 f"{n_her[HERKUNFT_BEIDE]} BA + Karriereseite, "
                 f"{n_her[HERKUNFT_SJ]} nur Karriereseite "
                 "(Blätter Gesamt-Übersicht, Alle Stellen = alle offenen; "
                 "Rohdaten data/stellen_alle.csv)")
    zs["A11"].font = Font(name=ARIAL, bold=True)

    # ---------------- ScrapJobs: Karriereseiten regionaler Arbeitgeber
    # Detailblaetter; der Abgleich mit der BA kommt aus baue_stellen_alle.
    if sj:
        sj_info = {r["scrapjobs_id"]: r for r in alle if r["scrapjobs_id"]}
        sj_offen = [r for r in sj if r.get("aktiv", "ja") == "ja"]

        def in_ba(r):
            return sj_info[r["id"]]["herkunft"] == HERKUNFT_BEIDE

        sl = wb.create_sheet("ScrapJobs")
        sl.append(["Arbeitgeber", "Stelle", "Ort", "Kreis", "Quelle", "Link",
                   "Veröffentlicht", "Erstmals gesehen", "Zuletzt gesehen",
                   "Aktuell offen", "Standzeit (Tage)", "Auch in BA-Daten",
                   "Branche"])
        for i, r in enumerate(sorted(
                sj, key=lambda r: (r.get("aktiv", "ja") != "ja",
                                   r["arbeitgeber"], r["titel"])), start=2):
            offen = r.get("aktiv", "ja") == "ja"
            werte = [r["arbeitgeber"], r["titel"], r["ort"],
                     kreis_von(r["ort"]), r["quelle"], r["url"],
                     r["veroeffentlicht"] or None, as_date(r["first_seen"]),
                     as_date(r["last_seen"]), "ja" if offen else "nein",
                     standzeit_tage(r), "ja" if in_ba(r) else "nein",
                     sj_info[r["id"]]["branche"]]
            for j, v in enumerate(werte, start=1):
                sl.cell(row=i, column=j, value=v)
            sl.cell(row=i, column=8).number_format = DATUM_FMT
            sl.cell(row=i, column=9).number_format = DATUM_FMT
        style_header(sl, 13)

        # Abgleich je Arbeitgeber (nur aktuell offene Karriereseiten-Stellen)
        sj_ag = {}
        for r in sj_offen:
            sj_ag.setdefault(r["arbeitgeber"], []).append(r)
        ba_offen_je_key = Counter(norm_ag(r["arbeitgeber"]) for r in log
                                  if ba_ist_offen(r, stand))
        sa = wb.create_sheet("ScrapJobs-Abgleich")
        sa.append(["Arbeitgeber", "Offen (Karriereseite)",
                   "davon auch in BA", "Nur auf Karriereseite",
                   "Offen in BA-Daten (Arbeitgeber)", "Abdeckung BA"])
        zeilen = []
        for a, rs in sj_ag.items():
            auch = sum(1 for r in rs if in_ba(r))
            k = norm_ag(a)
            ba_n = sum(n for b, n in ba_offen_je_key.items() if ag_passt(k, b))
            zeilen.append((a, len(rs), auch, len(rs) - auch, ba_n))
        zeilen.sort(key=lambda z: (-z[3], -z[1], z[0]))
        for i, (a, n, auch, nur, ba_n) in enumerate(zeilen, start=2):
            sa.cell(row=i, column=1, value=a)
            sa.cell(row=i, column=2, value=n)
            sa.cell(row=i, column=3, value=auch)
            sa.cell(row=i, column=4, value=nur)
            sa.cell(row=i, column=5, value=ba_n)
            sa.cell(row=i, column=6, value=auch / n).number_format = "0%"
        style_header(sa, 6)
        gn = sum(z[1] for z in zeilen)
        gauch = sum(z[2] for z in zeilen)
        sa.cell(row=len(zeilen) + 3, column=1, value="Gesamt").font = Font(
            name=ARIAL, bold=True)
        sa.cell(row=len(zeilen) + 3, column=2, value=gn)
        sa.cell(row=len(zeilen) + 3, column=3, value=gauch)
        sa.cell(row=len(zeilen) + 3, column=4, value=gn - gauch)
        sa.cell(row=len(zeilen) + 5, column=1, value=(
            "Abgleich: gleicher Arbeitgeber (Name ohne Rechtsform, "
            "ineinander enthalten), gleicher Stellentitel (ohne m/w/d) und "
            f"Zeitraum hoechstens {ABGLEICH_TOLERANZ_TAGE} Tage auseinander; "
            "jede BA-Stelle zaehlt hoechstens einmal. 'Nur auf Karriereseite' "
            "ist der Mehrwert gegenueber der BA-Auswertung."))
        stand_sj = {}
        try:
            with open(os.path.join(DATA, "scrapjobs_stand.json"),
                      encoding="utf-8") as fh:
                stand_sj = json.load(fh)
        except (OSError, ValueError):
            pass
        zs["A6"] = "Karriereseiten (ScrapJobs)"
        zs["B6"] = (f"{gn} offene Stellen bei {len(zeilen)} Arbeitgebern, "
                    f"davon {gn - gauch} nicht in den BA-Daten"
                    + (f"; Datenstand {stand_sj['aktualisiert'][:10]}, "
                       f"{stand_sj['quellen_ok']} von "
                       f"{stand_sj['quellen_gesamt']} Quellen gelesen"
                       if stand_sj.get("aktualisiert") else "")
                    + " (Blaetter ScrapJobs, ScrapJobs-Abgleich)")
        zs["A6"].font = Font(name=ARIAL, bold=True)

    # verbleibende Formeln (Relation zur blauen Spalte) beim Oeffnen
    # in Excel/LibreOffice sicher durchrechnen lassen
    wb.calculation.fullCalcOnLoad = True

    for ws in wb.worksheets:
        base_font(ws)
        autosize(ws)
    # Branchen: feste Breiten, sonst richten sich die Spalten nach den
    # langen Hinweis- und Berufstexten und die Tabelle wird unlesbar breit
    if "Branchen" in wb.sheetnames:
        bws = wb["Branchen"]
        breiten = {"A": 50, "B": 13, "C": 9, "D": 10, "E": 10, "F": 10,
                   "G": 10, "H": 12, "I": 18, "J": 13, "K": 13, "L": 13,
                   "M": 18}
        for col in range(1, bws.max_column + 1):
            bst = get_column_letter(col)
            bws.column_dimensions[bst].width = breiten.get(bst, 14)
    # ---------------- Boersen-Stichprobe (Adzuna, Google Jobs, Apify)
    api_roh = read_csv("api_jobs_log.csv")
    if api_roh:
        boersen = boersen_zeilen(api_roh, log)
        bs = wb.create_sheet("Börsen-Stichprobe")
        bs.append(["Stichprobe aus Börsen-APIs: je Tag ein rotierendes "
                   "Berufssegment, gedeckelt durch ein Tagesbudget. Nicht "
                   "hochrechenbar und nicht in Summen/Zeitreihen enthalten."])
        bs.append([])
        bs.append(["Branche", "Stellen", "davon nicht in BA-Daten",
                   "Anteil nicht in BA"])
        je_br = {}
        for r in boersen:
            z = je_br.setdefault(r["branche"], [0, 0])
            z[0] += 1
            z[1] += r["auch_bei_ba"] == "nein"
        for i, (br, (n, nur)) in enumerate(sorted(je_br.items()), start=4):
            bs.append([br, n, nur, f"=C{i}/B{i}"])
            bs.cell(row=i, column=4).number_format = "0%"
        style_header(bs, 4, row=3)
        zl = 5 + len(je_br)
        bs.cell(row=zl, column=1, value="Quelle / Börse").font = Font(name=ARIAL, bold=True)
        bs.cell(row=zl, column=2, value="Stellen").font = Font(name=ARIAL, bold=True)
        je_pt = Counter((r["quelle"], r["portal"]) for r in boersen)
        for k, ((q, pt), n) in enumerate(sorted(je_pt.items()), start=zl + 1):
            bs.cell(row=k, column=1, value=f"{q}: {pt}")
            bs.cell(row=k, column=2, value=n)
        sp = zl + len(je_pt) + 3
        kopf = ["Arbeitgeber", "Stelle", "Ort", "Branche", "Quelle", "Börse",
                "Suchbegriff", "Link", "Erstmals gesehen", "Zuletzt gesehen",
                "Auch in BA-Daten"]
        for j, v in enumerate(kopf, start=1):
            bs.cell(row=sp, column=j, value=v)
        style_header(bs, len(kopf), row=sp)
        for i, r in enumerate(sorted(boersen, key=lambda r: (r["arbeitgeber"], r["titel"])), start=sp + 1):
            for j, v in enumerate([r["arbeitgeber"], r["titel"], r["ort"],
                                   r["branche"], r["quelle"], r["portal"],
                                   r["suchbegriff"], r["url"],
                                   as_date(r["first_seen"]),
                                   as_date(r["last_seen"]),
                                   r["auch_bei_ba"]], start=1):
                bs.cell(row=i, column=j, value=v)
            bs.cell(row=i, column=9).number_format = DATUM_FMT
            bs.cell(row=i, column=10).number_format = DATUM_FMT
        laeufe = read_csv("api_laeufe.csv")
        if laeufe:
            kz = sp + len(boersen) + 3
            for j, v in enumerate(["Datum", "Quelle", "Segment", "Suchbegriff",
                                   "Abfragen", "Treffer roh", "Im Umkreis",
                                   "Neu", "Kosten (USD)", "Status"], start=1):
                bs.cell(row=kz, column=j, value=v)
            style_header(bs, 10, row=kz)
            for i, r in enumerate(sorted(laeufe, key=lambda r: (r["datum"], r["quelle"]), reverse=True), start=kz + 1):
                for j, f in enumerate(["datum", "quelle", "segment", "suchbegriff", "abfragen",
                                       "treffer_roh", "im_umkreis", "neu", "kosten_usd", "status"], start=1):
                    v = r[f]
                    bs.cell(row=i, column=j, value=float(v) if f == "kosten_usd" else
                            int(v) if f in ("abfragen", "treffer_roh", "im_umkreis", "neu") else v)
        autosize(bs)
        bs.freeze_panes = None

    # Gemeinsame/ScrapJobs-Blaetter direkt hinter die Zusammenfassung,
    # damit sie nicht hinter den langen BA-Blaettern verschwinden
    vorn = [n for n in ("Gesamt-Übersicht", "Alle Stellen", "ScrapJobs",
                        "ScrapJobs-Abgleich", "Börsen-Stichprobe")
            if n in wb.sheetnames]
    for pos, name in enumerate(vorn, start=1):
        ws = wb[name]
        wb.move_sheet(ws, offset=pos - wb.worksheets.index(ws))
    wb.save(OUT)
    print(f"Excel geschrieben: {OUT}")
    print(f"Stand {stand}, {len(daten)} Erhebungstage, "
          f"{len(log)} Stellen im Log.")
    return 0


if __name__ == "__main__":
    if "--nur-auswertung" not in sys.argv:
        main()
    raise SystemExit(build_excel())
