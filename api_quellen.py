"""Taegliche Stichprobe aus Boersen-APIs (Adzuna, Google Jobs/SerpApi, Apify).

Ergaenzt BA und Karriereseiten um Anzeigen, die dort fehlen (LinkedIn,
StepStone, XING, Indeed ...). Es ist bewusst eine **Stichprobe**: je Tag
ein Berufssegment (rotierend), gedeckelt durch ein Tagesbudget. Die
Ergebnisse stehen in eigenen Dateien und fliessen nicht in die
BA-Summen oder Zeitreihen ein.

Dateien (data/):
  api_jobs_log.csv  eine Zeile je Stelle (first_seen/last_seen)
  api_laeufe.csv    eine Zeile je Quelle und Tag (Treffer, Kosten, Status)

Zugangsdaten nur ueber Umgebungsvariablen; fehlt eine, wird die Quelle
uebersprungen. Ein Ausfall bricht den Datenlauf nie ab.

  ADZUNA_APP_ID, ADZUNA_APP_KEY   kostenloses Kontingent
  SERPAPI_API_KEY                 pro Suche kostenpflichtig
  APIFY_API_TOKEN                 pro Ergebnis kostenpflichtig
  API_BUDGET_USD                  Tagesbudget, Standard 0.25
  SERPAPI_USD_PRO_SUCHE           Standard 0.015

Trockenlauf ohne Abfragen:  python api_quellen.py --dry-run
"""
import csv
import hashlib
import json
import os
import re
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

ORT = "Waiblingen"
RADIUS_KM = 50
START = date(2026, 11, 25)          # Tag 0 der Rotation
TIMEOUT = 60

BUDGET_USD = float(os.environ.get("API_BUDGET_USD", "").strip() or 0.25)
SERPAPI_USD = float(os.environ.get("SERPAPI_USD_PRO_SUCHE", "").strip() or 0.015)
SERPAPI_SEITEN = 5                  # je 10 Stellen
ADZUNA_SEITEN = 2                   # je 50 Stellen
APIFY_ACTOR = os.environ.get("APIFY_JOBFEED_ACTOR", "").strip() or "3HJWd9KfGyItAD5N9"
APIFY_MAX_ITEMS = 100
APIFY_MAX_CHARGE_USD = 0.15
APIFY_USD_PRO_ITEM = 0.001          # Schaetzung, falls das Preismodell fehlt
# Boersen, die wir schon direkt abfragen
APIFY_AUSSCHLUSS = re.compile(r"arbeitsagentur|jobb(ö|oe)rse|bundesagentur", re.I)
# Gemeinden im Umkreis fuer das Orts-Regex des Job-Feed (Treffer werden
# danach nochmals mit umkreis.im_umkreis geprueft)
APIFY_ORTE = ["Waiblingen", "Stuttgart", "Fellbach", "Schorndorf", "Backnang",
              "Winnenden", "Esslingen", "Ludwigsburg", "Göppingen",
              "Schwäbisch Gmünd", "Kornwestheim", "Leonberg", "Böblingen",
              "Sindelfingen", "Heilbronn", "Murrhardt", "Welzheim", "Remseck",
              "Ostfildern", "Filderstadt", "Nürtingen", "Kirchheim", "Marbach",
              "Vaihingen", "Gaildorf", "Schwäbisch Hall"]

# Je Berufssegment (branchen.SEGMENTE) typische Suchbegriffe
SUCHBEGRIFFE = {
    "S11": ["Gärtner", "Landwirt", "Forstwirt", "Florist"],
    "S12": ["Produktionshelfer", "Maschinenbediener", "Schweißer", "Schreiner"],
    "S13": ["Industriemechaniker", "Elektroniker", "Mechatroniker", "Konstrukteur"],
    "S14": ["Maurer", "Elektriker", "Anlagenmechaniker SHK", "Maler"],
    "S21": ["Koch", "Bäcker", "Hotelfachmann", "Servicekraft Gastronomie"],
    "S22": ["Pflegefachkraft", "Medizinische Fachangestellte", "Physiotherapeut", "Arzt"],
    "S23": ["Erzieher", "Sozialarbeiter", "Lehrer", "Heilerziehungspfleger"],
    "S31": ["Verkäufer", "Einzelhandel", "Vertriebsmitarbeiter", "Einkäufer"],
    "S32": ["Büroangestellter", "Sachbearbeiter", "Assistenz Geschäftsführung", "Projektleiter"],
    "S33": ["Buchhalter", "Steuerfachangestellter", "Personalreferent", "Marketing Manager"],
    "S41": ["Softwareentwickler", "IT Administrator", "Data Analyst", "Chemielaborant"],
    "S51": ["Sicherheitsmitarbeiter", "Werkschutz", "Pförtner", "Brandschutzbeauftragter"],
    "S52": ["Lagerarbeiter", "Staplerfahrer", "Berufskraftfahrer", "Fachkraft Lagerlogistik"],
    "S53": ["Reinigungskraft", "Gebäudereiniger", "Hausmeister", "Reinigungskraft Krankenhaus"],
}
SEGMENT_REIHE = list(SUCHBEGRIFFE)

LOG_FELDER = ["id", "quelle", "portal", "arbeitgeber", "titel", "ort", "url",
              "veroeffentlicht", "suchbegriff", "segment", "first_seen",
              "last_seen"]
LAUF_FELDER = ["datum", "quelle", "segment", "suchbegriff", "abfragen",
               "treffer_roh", "im_umkreis", "neu", "kosten_usd", "status"]


# ---------------------------------------------------------------- Plan
def tages_plan(tag: date):
    """(Segment, Suchbegriff) des Tages: Segment rotiert taeglich, der
    Begriff wechselt jeweils nach einem vollen Segmentdurchlauf."""
    n = (tag - START).days
    seg = SEGMENT_REIHE[n % len(SEGMENT_REIHE)]
    begriffe = SUCHBEGRIFFE[seg]
    return seg, begriffe[(n // len(SEGMENT_REIHE)) % len(begriffe)]


# ---------------------------------------------------------------- HTTP
class QuellenFehler(Exception):
    pass


def http_json(url, daten=None, headers=None):
    """GET (daten=None) oder POST mit JSON; Antwort als Python-Objekt.
    Fehlertexte enthalten nie die URL (sie kann Schluessel tragen)."""
    body = None if daten is None else json.dumps(daten).encode("utf-8")
    h = {"Accept": "application/json", "User-Agent": "arbeitsmarkt-monitor"}
    if body is not None:
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(url, data=body, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise QuellenFehler(f"HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise QuellenFehler(type(e).__name__) from None


# ---------------------------------------------------------------- Quellen
def _text(x):
    return " ".join(str(x or "").split())


def _id(quelle, eigene_id, titel, firma, ort):
    if eigene_id:
        return f"{quelle}:{eigene_id}"
    h = hashlib.sha1("|".join((titel, firma, ort)).casefold().encode()).hexdigest()
    return f"{quelle}:{h[:16]}"


def adzuna(begriff, http=http_json):
    """-> (stellen, abfragen, kosten_usd)"""
    app_id = os.environ.get("ADZUNA_APP_ID", "").strip()
    app_key = os.environ.get("ADZUNA_APP_KEY", "").strip()
    if not app_id or not app_key:
        raise QuellenFehler("kein Zugang")
    stellen, abfragen = [], 0
    for seite in range(1, ADZUNA_SEITEN + 1):
        q = urllib.parse.urlencode({
            "app_id": app_id, "app_key": app_key, "results_per_page": 50,
            "what": begriff, "where": ORT, "distance": RADIUS_KM,
            "sort_by": "date", "content-type": "application/json"})
        data = http(f"https://api.adzuna.com/v1/api/jobs/de/search/{seite}?{q}")
        abfragen += 1
        rows = data.get("results") or []
        for j in rows:
            titel = _text(j.get("title"))
            firma = _text((j.get("company") or {}).get("display_name"))
            ort = _text((j.get("location") or {}).get("display_name"))
            stellen.append({
                "id": _id("ADZUNA", str(j.get("id") or ""), titel, firma, ort),
                "quelle": "Adzuna", "portal": "Adzuna", "arbeitgeber": firma,
                "titel": titel, "ort": ort, "url": j.get("redirect_url") or "",
                "veroeffentlicht": (j.get("created") or "")[:10]})
        if len(rows) < 50:
            break
    return stellen, abfragen, 0.0


def google_jobs(begriff, restbudget, http=http_json):
    key = os.environ.get("SERPAPI_API_KEY", "").strip()
    if not key:
        raise QuellenFehler("kein Zugang")
    stellen, abfragen, token = [], 0, None
    while abfragen < SERPAPI_SEITEN and (abfragen + 1) * SERPAPI_USD <= restbudget:
        p = {"engine": "google_jobs", "q": begriff, "api_key": key,
             "gl": "de", "hl": "de", "google_domain": "google.de",
             "location": "Waiblingen, Baden-Württemberg, Germany",
             "lrad": RADIUS_KM}
        if token:
            p["next_page_token"] = token
        data = http("https://serpapi.com/search.json?" + urllib.parse.urlencode(p))
        abfragen += 1
        if data.get("error"):
            if abfragen == 1 and not data.get("jobs_results"):
                raise QuellenFehler(_text(data["error"])[:80])
            break
        for j in data.get("jobs_results") or []:
            titel, firma = _text(j.get("title")), _text(j.get("company_name"))
            ort = _text(j.get("location"))
            opt = (j.get("apply_options") or [{}])[0]
            stellen.append({
                "id": _id("GOOGLE", str(j.get("job_id") or "")[:60], titel, firma, ort),
                "quelle": "Google Jobs", "portal": _text(j.get("via")).removeprefix("über ").removeprefix("via ") or "Google Jobs",
                "arbeitgeber": firma, "titel": titel, "ort": ort,
                "url": opt.get("link") or j.get("share_link") or "",
                "veroeffentlicht": _text((j.get("detected_extensions") or {}).get("posted_at"))})
        token = (data.get("serpapi_pagination") or {}).get("next_page_token")
        if not token:
            break
    return stellen, abfragen, round(abfragen * SERPAPI_USD, 6)


def _regex_ort():
    return "(^|[^A-Za-zÄÖÜäöüß])(" + "|".join(
        "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else re.escape(c) for c in o)
        for o in APIFY_ORTE) + ")([^A-Za-zÄÖÜäöüß]|$)"


def _titel_regex(begriff):
    return "".join(f"[{c.lower()}{c.upper()}]" if c.isalpha() else re.escape(c) for c in begriff)


def _pick(item, felder):
    for f in felder:
        v = item.get(f)
        if isinstance(v, str) and v.strip():
            return _text(v)
        if isinstance(v, dict):
            for k in ("name", "display_name", "city"):
                if isinstance(v.get(k), str) and v[k].strip():
                    return _text(v[k])
    return ""


def apify(begriff, restbudget, http=http_json):
    token = os.environ.get("APIFY_API_TOKEN", "").strip()
    if not token:
        raise QuellenFehler("kein Zugang")
    limit = min(APIFY_MAX_CHARGE_USD, restbudget)
    if limit < 0.01:
        raise QuellenFehler("Budget aufgebraucht")
    eingabe = {"country": "germany", "title": _titel_regex(begriff),
               "location": _regex_ort(), "limit": APIFY_MAX_ITEMS, "skip": 0,
               "sort_field": "datetime_from", "sort_direction": -1}
    url = (f"https://api.apify.com/v2/acts/{urllib.parse.quote(APIFY_ACTOR)}/runs?"
           + urllib.parse.urlencode({"maxItems": APIFY_MAX_ITEMS,
                                     "maxTotalChargeUsd": limit, "waitForFinish": 300}))
    auth = {"Authorization": f"Bearer {token}"}
    run = (http(url, eingabe, auth) or {}).get("data") or {}
    if run.get("status") not in ("SUCCEEDED", "TIMED-OUT", "ABORTED") and not run.get("defaultDatasetId"):
        raise QuellenFehler(f"Lauf {run.get('status') or 'ohne Ergebnis'}")
    items = http(f"https://api.apify.com/v2/datasets/{run['defaultDatasetId']}/items?"
                 + urllib.parse.urlencode({"clean": 1, "limit": APIFY_MAX_ITEMS}),
                 None, auth)
    stellen = []
    for it in items if isinstance(items, list) else []:
        site = _text(it.get("site"))
        url_ = _pick(it, ["url", "jobUrl", "link", "applyUrl"])
        if APIFY_AUSSCHLUSS.search(site) or "arbeitsagentur.de" in url_:
            continue
        titel = _pick(it, ["title", "jobTitle", "position", "name"])
        firma = _pick(it, ["companyName", "company", "company_name", "employer"])
        ort = _pick(it, ["location", "jobLocation", "city", "place"])
        stellen.append({
            "id": _id("APIFY", re.sub(r"[^A-Za-z0-9_-]", "", str(it.get("id") or it.get("jobId") or ""))[:80],
                      titel, firma, ort),
            "quelle": "Apify", "portal": site or "Job-Feed", "arbeitgeber": firma,
            "titel": titel, "ort": ort, "url": url_,
            "veroeffentlicht": _pick(it, ["postedAt", "datetime_from", "publishedAt", "date"])[:10]})
    usage = float(run.get("usageTotalUsd") or 0)
    p = run.get("pricingInfo") or {}
    berechnet = 0.0
    if p.get("pricingModel") == "PRICE_PER_DATASET_ITEM":
        berechnet = len(items if isinstance(items, list) else []) * float(p.get("pricePerUnitUsd") or 0)
    elif p.get("pricingModel") == "PAY_PER_EVENT":
        preise = p.get("pricingPerEvent", {}).get("actorChargeEvents", {})
        for ev, n in (run.get("chargedEventCounts") or {}).items():
            berechnet += float(n or 0) * float((preise.get(ev) or {}).get("eventPriceUsd") or 0)
    kosten = max(usage + berechnet, len(stellen) * APIFY_USD_PRO_ITEM)
    return stellen, 1, round(kosten, 6)


# ---------------------------------------------------------------- Lauf
def _lies(pfad, felder):
    if not pfad.exists():
        return []
    with pfad.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _schreibe(pfad, felder, rows):
    with pfad.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=felder, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sammle(today, data_dir=None, quellen=None, budget=None):
    """Die Tagesabfrage ausfuehren und beide CSV-Dateien fortschreiben.

    quellen: Dict Name -> Funktion(begriff, restbudget) -> (stellen, abfragen,
    kosten); Standard sind die echten Abfragen (fuer Tests austauschbar).
    """
    data_dir = Path(data_dir or DATA_DIR)
    data_dir.mkdir(exist_ok=True)
    budget = BUDGET_USD if budget is None else budget
    if quellen is None:
        quellen = {"Adzuna": lambda b, r: adzuna(b),
                   "Apify": lambda b, r: apify(b, r),
                   "Google Jobs": lambda b, r: google_jobs(b, r)}
    tag = date.fromisoformat(today)
    segment, begriff = tages_plan(tag)
    laeufe = _lies(data_dir / LAEUFE, LAUF_FELDER)
    log = {r["id"]: r for r in _lies(data_dir / LOG, LOG_FELDER)}
    heute = {r["quelle"] for r in laeufe if r["datum"] == today and r["status"] == "ok"}
    rest = budget - sum(float(r["kosten_usd"] or 0) for r in laeufe if r["datum"] == today)

    for name, abfrage in quellen.items():
        if name in heute:
            print(f"[api] {name}: heute schon abgefragt")
            continue
        zeile = {"datum": today, "quelle": name, "segment": segment,
                 "suchbegriff": begriff, "abfragen": 0, "treffer_roh": 0,
                 "im_umkreis": 0, "neu": 0, "kosten_usd": 0.0, "status": "ok"}
        try:
            stellen, zeile["abfragen"], zeile["kosten_usd"] = abfrage(begriff, rest)
            rest -= zeile["kosten_usd"]
            zeile["treffer_roh"] = len(stellen)
            for s in stellen:
                if not s["titel"] or not im_umkreis(s["ort"]):
                    continue
                zeile["im_umkreis"] += 1
                alt = log.get(s["id"])
                if alt:
                    alt["last_seen"] = today
                    continue
                zeile["neu"] += 1
                log[s["id"]] = {**s, "suchbegriff": begriff, "segment": segment,
                                "first_seen": today, "last_seen": today}
        except QuellenFehler as e:
            zeile["status"] = "uebersprungen: " + str(e) if str(e) in ("kein Zugang", "Budget aufgebraucht") else "fehler: " + str(e)
            print(f"[api] {name}: {zeile['status']}", file=sys.stderr)
        except Exception as e:      # nie den Datenlauf stoppen
            zeile["status"] = "fehler: " + type(e).__name__
            print(f"[api] {name}: {zeile['status']}", file=sys.stderr)
        laeufe = [r for r in laeufe if not (r["datum"] == today and r["quelle"] == name)]
        laeufe.append(zeile)
        print(f"[api] {name}: {zeile['status']}, {zeile['im_umkreis']} im Umkreis "
              f"({zeile['neu']} neu), {zeile['kosten_usd']} USD")
    _schreibe(data_dir / LAEUFE, LAUF_FELDER, laeufe)
    _schreibe(data_dir / LOG, LOG_FELDER, log.values())
    return list(log.values())


def main(argv):
    if "--dry-run" in argv:
        seg, begriff = tages_plan(date.today())
        print(f"Segment {seg}, Suchbegriff '{begriff}', Budget {BUDGET_USD} USD, "
              f"SerpApi bis {SERPAPI_SEITEN} Suchen a {SERPAPI_USD} USD, "
              f"Apify max {APIFY_MAX_CHARGE_USD} USD")
        for n, v in (("Adzuna", "ADZUNA_APP_KEY"), ("Google Jobs", "SERPAPI_API_KEY"),
                     ("Apify", "APIFY_API_TOKEN")):
            print(f"  {n}: {'Zugang vorhanden' if os.environ.get(v) else 'kein Zugang'}")
        return
    sammle(date.today().isoformat())


if __name__ == "__main__":
    main(sys.argv[1:])
