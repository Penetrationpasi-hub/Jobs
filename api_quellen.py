"""Boersen-Stichprobe (Adzuna, Google Jobs, Apify) aus Netlify abholen.

Die taeglichen Abfragen laufen in der App (Repo N-chster-Schritt2, geplante
Netlify-Funktionen boersen-*) mit den dort hinterlegten Schluesseln. Dieses
Modul holt nur das Ergebnis ueber den oeffentlichen Lese-Link
`<BOERSEN_URL>/api/boersen-export?seit=JJJJ-MM-TT`, wendet den
50-km-Filter an (umkreis.im_umkreis) und schreibt zwei Dateien:

  data/api_jobs_log.csv  eine Zeile je Stelle (first_seen/last_seen)
  data/api_laeufe.csv    eine Zeile je Quelle und Tag (Treffer, Kosten, Status)

Es ist eine **Stichprobe** (je Tag ein rotierendes Berufssegment, Tagesbudget
in Netlify), keine Vollerhebung. Sie fliesst nicht in BA-Summen oder
Zeitreihen ein. Keine Zugangsdaten noetig; fehlt BOERSEN_URL oder ist
Netlify nicht erreichbar, wird uebersprungen. Der Datenlauf bricht nie ab.

Pruefen ohne Schreiben:  python api_quellen.py --dry-run
"""
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from umkreis import im_umkreis

DATA_DIR = Path(__file__).resolve().parent / "data"
LOG = "api_jobs_log.csv"
LAEUFE = "api_laeufe.csv"
START = "2026-11-25"                # erster moegliche Tag der Rotation
TIMEOUT = 60

LOG_FELDER = ["id", "quelle", "portal", "arbeitgeber", "titel", "ort", "url",
              "veroeffentlicht", "suchbegriff", "segment", "first_seen",
              "last_seen"]
LAUF_FELDER = ["datum", "quelle", "segment", "suchbegriff", "abfragen",
               "treffer_roh", "im_umkreis", "neu", "kosten_usd", "status"]


class QuellenFehler(Exception):
    pass


def boersen_url():
    return os.environ.get("BOERSEN_URL", "").strip().rstrip("/")


def hole_export(seit, base=None):
    """Abgeschlossene Tage ab `seit` aus Netlify (Liste von Tages-Dicts)."""
    base = base or boersen_url()
    if not base.startswith("https://"):
        raise QuellenFehler("BOERSEN_URL fehlt oder ist kein https-Link")
    url = f"{base}/api/boersen-export?" + urllib.parse.urlencode({"seit": seit})
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "arbeitsmarkt-monitor"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            doc = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise QuellenFehler(f"HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise QuellenFehler(type(e).__name__) from None
    tage = doc.get("tage") if isinstance(doc, dict) else None
    if not isinstance(tage, list):
        raise QuellenFehler("unerwartete Antwort")
    return tage


def _lies(pfad):
    if not pfad.exists():
        return []
    with pfad.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _schreibe(pfad, felder, rows):
    with pfad.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _text(x, n):
    return " ".join(str(x or "").split())[:n]


def sammle(today, data_dir=None, export=None):
    """Neue Tage aus Netlify uebernehmen. `export(seit)` ist fuer Tests
    austauschbar. Rueckgabe: alle bekannten Stellen."""
    data_dir = Path(data_dir or DATA_DIR)
    data_dir.mkdir(exist_ok=True)
    laeufe = _lies(data_dir / LAEUFE)
    log = {r["id"]: r for r in _lies(data_dir / LOG)}
    bekannt = {(r["datum"], r["quelle"]) for r in laeufe}
    seit = max((r["datum"] for r in laeufe), default=START)
    try:
        tage = (export or hole_export)(seit)
    except QuellenFehler as e:
        print(f"[api] Netlify-Export uebersprungen: {e}", file=sys.stderr)
        return list(log.values())
    neue_tage = 0
    for tag in sorted(tage, key=lambda t: t.get("datum", "")):
        datum = tag.get("datum", "")
        if not datum or datum > today:
            continue
        segment, begriff = tag.get("segment", ""), tag.get("suchbegriff", "")
        zeilen = {}
        for l in tag.get("laeufe") or []:
            if (datum, l.get("quelle", "")) in bekannt:
                continue
            zeilen[l["quelle"]] = {
                "datum": datum, "quelle": l["quelle"], "segment": segment,
                "suchbegriff": begriff, "abfragen": int(l.get("abfragen") or 0),
                "treffer_roh": int(l.get("treffer_roh") or 0), "im_umkreis": 0,
                "neu": 0, "kosten_usd": float(l.get("kosten_usd") or 0),
                "status": _text(l.get("status"), 120)}
        if not zeilen:
            continue
        neue_tage += 1
        for s in tag.get("stellen") or []:
            z = zeilen.get(s.get("quelle"))
            titel, ort = _text(s.get("titel"), 200), _text(s.get("ort"), 100)
            sid = _text(s.get("id"), 100)
            if z is None or not sid or not titel or not im_umkreis(ort):
                continue
            z["im_umkreis"] += 1
            alt = log.get(sid)
            if alt:
                alt["last_seen"] = max(alt["last_seen"], datum)
                continue
            z["neu"] += 1
            log[sid] = {
                "id": sid, "quelle": s["quelle"],
                "portal": _text(s.get("portal"), 60),
                "arbeitgeber": _text(s.get("arbeitgeber"), 150),
                "titel": titel, "ort": ort, "url": _text(s.get("url"), 500),
                "veroeffentlicht": _text(s.get("veroeffentlicht"), 30),
                "suchbegriff": begriff, "segment": segment,
                "first_seen": datum, "last_seen": datum}
        laeufe.extend(zeilen.values())
        print(f"[api] {datum} ({segment}, '{begriff}'): "
              + ", ".join(f"{z['quelle']} {z['im_umkreis']} im Umkreis "
                          f"({z['neu']} neu, {z['status']})"
                          for z in zeilen.values()))
    _schreibe(data_dir / LAEUFE, LAUF_FELDER, laeufe)
    _schreibe(data_dir / LOG, LOG_FELDER, log.values())
    if not neue_tage:
        print("[api] keine neuen Tage in Netlify")
    return list(log.values())


def main(argv):
    if "--dry-run" in argv:
        laeufe = _lies(DATA_DIR / LAEUFE)
        seit = max((r["datum"] for r in laeufe), default=START)
        print(f"BOERSEN_URL: {boersen_url() or '(nicht gesetzt)'}; letzter Tag im Log: {seit}")
        try:
            tage = hole_export(seit)
        except QuellenFehler as e:
            print(f"Export nicht abrufbar: {e}")
            return
        for t in tage:
            print(f"  {t['datum']} {t.get('segment')} '{t.get('suchbegriff')}': "
                  f"{len(t.get('stellen') or [])} Stellen roh")
        return
    sammle(date.today().isoformat())


if __name__ == "__main__":
    main(sys.argv[1:])
