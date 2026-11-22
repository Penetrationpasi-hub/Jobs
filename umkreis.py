"""Gemeinsamer, offline reproduzierbarer 50-km-Filter fuer alle Stellenquellen.

Ohne Strassenadresse verwenden wir Orts-/PLZ-Koordinaten von GeoNames.
Unbekannte oder mehrdeutige Ortsangaben werden nicht als lokale Jobs gezaehlt.
"""
import csv
import json
import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

REGION = "waiblingen_50km"
RADIUS_KM = 50
ZENTRUM = (48.8324, 9.3164)
DATA = Path(__file__).resolve().parent / "data"


def norm(text):
    text = (text or "").casefold().replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def entfernung(lat, lon):
    a, b = map(math.radians, ZENTRUM)
    c, d = math.radians(lat), math.radians(lon)
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 6371.0088 * 2 * math.asin(min(1, math.sqrt(h)))


# BA-Ortsnamen mit regionalem Zusatz bzw. lokale Kurzformen.
ALIASES = {
    "waiblingen rems": "71332", "korb remstal": "71404",
    "urbach rems": "73660", "rommelshausen": "71394",
    "winterbach bei schorndorf wuertt": "73650", "aichwald schurw": "73773",
    "oberrot bei gaildorf": "74420", "aspach bei backnang": "71546",
    "gschwend bei gaildorf": "74417", "eschach bei schwaebisch gmuend": "73569",
    "ruppertshofen bei schwaebisch gmuend": "73577", "hochdorf bei plochingen": "73269",
    "kaisersbach im welzheimer wald": "73667", "altdorf bei nuertingen": "72655",
    "tannhausen bei ellwangen jagst": "73497", "heuchlingen lein": "73572",
    "flein bei heilbronn neckar": "74223", "talheim neckar": "74388",
    "wangen kreis goeppingen": "73117", "michelfeld kreis schwaebisch hall": "74545",
    "moeglingen kreis ludwigsburg wuertt": "71696", "boertlingen kreis goeppingen": "73104",
    "aichelberg kreis goeppingen": "73101", "birenbach kreis goeppingen": "73102",
    "allmersbach": "71573", "esslingen": "73728", "grunbach": "73630",
}


@lru_cache(maxsize=1)
def index():
    doc = json.loads((DATA / "geo_orte.json").read_text(encoding="utf-8"))
    names, postal = defaultdict(list), defaultdict(list)
    for plz, name, lat, lon, state in doc["orte"]:
        point = (lat, lon, state)
        names[norm(name)].append(point)
        postal[plz].append(point)
    pattern = re.compile(r"(?<!\w)(" + "|".join(
        map(re.escape, sorted(set(names) | set(ALIASES), key=lambda n: (-len(n), n)))) + r")(?!\w)")
    return names, postal, pattern


@lru_cache(maxsize=8192)
def pruefe_ort(ort):
    """(Status, km): innerhalb / ausserhalb / unklar; mehrere Orte konservativ.

    Alle erkannten Standorte muessen im Radius liegen. Bei gemischten oder
    nicht lokalisierbaren Angaben keine Aufnahme in die lokale Auswertung.
    """
    text = norm(ort)
    if not text:
        return "unklar", None
    # Auslands-PLZ duerfen nicht zufaellig als deutsche PLZ erkannt werden.
    if re.search(r"\b(remote|bundesweit|deutschlandweit|aussendienst|vereinigtes|"
                 r"oesterreich|schweiz|frankreich|italien|spanien|china|"
                 r"ch|at|fr|it|gb|uk|us|il|ca|lt|hu|be|rs|cl|se|pl|cz|nl)\b", text):
        return "unklar", None
    names, postal, pattern = index()
    points = []
    codes = re.findall(r"(?<!\d)\d{5}(?!\d)", ort)
    if codes:
        if any(code not in postal for code in codes):
            return "unklar", None
        for code in codes:
            points.extend(postal[code])
    else:
        matches = list(pattern.finditer(text))
        if not matches:
            return "unklar", None
        for match in matches:
            name = match.group()
            candidates = postal[ALIASES[name]] if name in ALIASES else names[name]
            if re.search(r"\b(wuerttemberg|wuertt|baden|bw)\b", text):
                candidates = [p for p in candidates if p[2] == "Baden-Württemberg"]
            if not candidates:
                return "unklar", None
            points.extend(candidates)
    distances = [entfernung(lat, lon) for lat, lon, _ in points]
    if max(distances) <= RADIUS_KM:
        return "innerhalb", max(distances)
    if min(distances) > RADIUS_KM:
        return "ausserhalb", min(distances)
    return "unklar", None


def im_umkreis(ort):
    return pruefe_ort(ort)[0] == "innerhalb"


def filter_stellen(rows):
    return [r for r in rows if im_umkreis(r.get("ort", ""))]


def schreibe_pruefung(log, sj, target):
    """Aggregierte Pruefliste auch fuer ausgeschlossene/fehlende Ortsangaben."""
    counts = Counter((source, r.get("ort", ""))
                     for source, rows in (("BA", log), ("Karriereseite", sj)) for r in rows)
    with Path(target).open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["herkunft", "ort", "stellen", "umkreis_status", "entfernung_km"])
        for (source, ort), n in sorted(counts.items()):
            status, km = pruefe_ort(ort)
            w.writerow([source, ort, n, status, round(km, 2) if km is not None else ""])


def zeitreihen(log, snapshots, beobachtungen):
    """Altdaten: angenommene Laufzeit, neue Tage: tatsaechliche Beobachtungen.

    Keine Hochrechnung alter, raeumlich unpassender Suchgebiets-Summen.
    Neue Tagesbeobachtungen haben Vorrang, auch bei einem leeren Ergebnis.
    """
    days = sorted({r["datum"] for r in snapshots})
    exact_days = {r["datum"] for r in snapshots if r["region"] == REGION}
    exact = defaultdict(dict)
    for r in filter_stellen(beobachtungen):
        exact[r["datum"]][r["refnr"]] = r
    snaps, berufe = [], []
    for day in days:
        if day in exact_days:
            rows = list(exact[day].values())
            method = "Tagesbeobachtungen"
        else:
            rows = [r for r in log if r["first_seen"] <= day <= r["last_seen"]]
            method = "Rekonstruktion first_seen/last_seen (Naeherung)"
        counts = Counter(r["beruf"] for r in rows)
        snaps.append({"datum": day, "region": REGION, "stellen_gesamt": len(rows),
                      "stellen_geladen": len(rows), "methode": method})
        berufe.extend({"datum": day, "region": REGION, "beruf": b, "anzahl": n}
                      for b, n in sorted(counts.items()))
    return berufe, snaps
