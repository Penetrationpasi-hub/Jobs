#!/usr/bin/env python3
"""
KldB-2010-Code je BA-Berufsbezeichnung ueber die BERUFENET-API der BA.

Die Jobsuche liefert nur den Berufsnamen (z.B. "Industriemechaniker/in").
BERUFENET kennt dieselben Namen und den zugehoerigen KldB-2010-Code; daraus
leitet branchen.py Berufshauptgruppe, Berufssegment und -sektor ab.

  Suche:   GET https://rest.arbeitsagentur.de/infosysbub/bnet/pc/v1/berufe
               ?suchwoerter=<Name>&page=0
  Detail:  GET .../berufe/<id>   -> Feld "kldb2010-Code" (z.B. "B 25102")
  Header:  X-API-Key: infosysbub-berufenet  (oeffentliche clientId)

Nur Treffer mit (normalisiert) GLEICHEM Namen werden uebernommen; alles
andere wird als quelle=offen vermerkt (branchen.py nutzt dann den
Stichwort-Rueckfall) und nach KLDB_WIEDERHOLEN_TAGE erneut versucht.

Inkrementell und hoeflich wie tools/ba_berufe.py: haeufigste Berufe zuerst,
hoechstens KLDB_MAX neue Abfragen je Lauf, Pause zwischen Requests,
bei 429 sofort Schluss, jeder Treffer wird sofort gespeichert.

  python tools/kldb_zuordnung.py           # normaler Lauf
  python tools/kldb_zuordnung.py --probe   # Rohantworten ins Log (Diagnose)

Output: data/beruf_kldb.csv
"""

import csv
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from branchen import HAUPTGRUPPEN, KLDB_DATEI, KLDB_FELDER, kldb_ziffern  # noqa: E402

API = "https://rest.arbeitsagentur.de/infosysbub/bnet/pc/v1/berufe"
HEADERS = {
    "X-API-Key": "infosysbub-berufenet",
    "User-Agent": "ba-jobmonitor/1.0 (privates Arbeitsmarkt-Monitoring)",
    "Accept": "application/json",
}
MAX_NEU = int(os.environ.get("KLDB_MAX", "400"))
PAUSE = float(os.environ.get("KLDB_PAUSE", "0.5"))
WIEDERHOLEN_TAGE = int(os.environ.get("KLDB_WIEDERHOLEN_TAGE", "30"))
KLDB_RE = re.compile(r"\bB\s?(\d{5})\b")


class Gedrosselt(Exception):
    """BA antwortet mit 429 - fuer diesen Lauf aufhoeren."""


def holen(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    fehler = None
    for versuch in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                raise Gedrosselt()
            fehler = e
        except Exception as e:  # Netzwerk, JSON
            fehler = e
        time.sleep(2 * (versuch + 1))
    raise RuntimeError(f"Abruf fehlgeschlagen: {url}: {fehler}")


def norm(name: str) -> str:
    return re.sub(r"[^a-zäöüß0-9]", "", (name or "").lower())


def _dicts(obj):
    """Alle dicts in einer verschachtelten JSON-Struktur."""
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _dicts(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _dicts(v)


def _name_von(d: dict) -> str:
    for k in ("kurzBezeichnungNeutral", "kurzbezeichnungNeutral",
              "kurzBezeichnung", "bezeichnungNeutral", "bezeichnung",
              "kurzbezeichnung", "name"):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for k, v in d.items():
        if "bezeichnung" in k.lower() and isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def kandidaten(antwort):
    """Suchantwort -> [(id, name)] (robust gegen unbekannte Feldnamen)."""
    out, gesehen = [], set()
    for d in _dicts(antwort):
        bid = d.get("id") or d.get("berufId") or d.get("dkzId")
        name = _name_von(d)
        if bid is not None and name and str(bid) not in gesehen:
            gesehen.add(str(bid))
            out.append((str(bid), name))
    return out


def kldb_aus(antwort) -> str:
    """KldB-5-Steller aus einer Detailantwort (Feld mit 'kldb' im Namen)."""
    for d in _dicts(antwort):
        for k, v in d.items():
            if "kldb" in k.lower() and isinstance(v, (str, int)):
                z = kldb_ziffern(str(v))
                if len(z) == 5:
                    return z
    m = KLDB_RE.search(json.dumps(antwort, ensure_ascii=False))
    return m.group(1) if m else ""


def suchbegriffe(beruf: str):
    """Voller Name, danach ohne Gender-/Schwerpunktzusaetze."""
    yield beruf
    kurz = re.split(r"\s+-\s+|\s*\(", beruf)[0]
    kurz = re.sub(r"/-?\w*|/in\b", "", kurz).strip()
    if kurz and kurz != beruf:
        yield kurz


def nachschlagen(beruf: str):
    """-> (kldb, berufenet_id, berufenet_name) oder (\"\", \"\", bester Name)."""
    ziel = norm(beruf)
    bester = ""
    for q in suchbegriffe(beruf):
        url = f"{API}?{urllib.parse.urlencode({'suchwoerter': q, 'page': 0})}"
        antwort = holen(url)
        time.sleep(PAUSE)
        kands = kandidaten(antwort) if antwort else []
        if kands and not bester:
            bester = kands[0][1]
        for bid, name in kands:
            if norm(name) == ziel:
                detail = holen(f"{API}/{urllib.parse.quote(bid)}")
                time.sleep(PAUSE)
                code = kldb_aus(detail) if detail else ""
                if not code:
                    code = kldb_aus({"x": [d for d in _dicts(antwort)
                                           if str(d.get("id")) == bid]})
                if code and code[:2] in HAUPTGRUPPEN:
                    return code, bid, name
                return "", bid, name
    return "", "", bester


def berufe_nach_haeufigkeit():
    c = Counter()
    for datei, feld, gewicht in (("berufe.csv", "beruf", "anzahl"),
                                 ("jobs_log.csv", "beruf", None)):
        pfad = BASE / "data" / datei
        if not pfad.exists():
            continue
        with pfad.open(encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                b = (r.get(feld) or "").strip()
                if b and b != "unbekannt":
                    c[b] += int(r.get(gewicht) or 1) if gewicht else 1
    return [b for b, _ in c.most_common()]


def laden_cache():
    if not os.path.exists(KLDB_DATEI):
        return {}
    with open(KLDB_DATEI, encoding="utf-8-sig", newline="") as f:
        return {r["beruf"]: r for r in csv.DictReader(f)}


def speichern(cache):
    tmp = KLDB_DATEI + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=KLDB_FELDER)
        w.writeheader()
        for b in sorted(cache):
            w.writerow({k: cache[b].get(k, "") for k in KLDB_FELDER})
    os.replace(tmp, KLDB_DATEI)


def probe():
    for q in ("Industriemechaniker/in", "Friseur/in"):
        url = f"{API}?{urllib.parse.urlencode({'suchwoerter': q, 'page': 0})}"
        a = holen(url)
        print(f"--- Suche {q}:\n{json.dumps(a, ensure_ascii=False)[:3000]}")
        k = kandidaten(a) if a else []
        print(f"--- Kandidaten: {k[:10]}")
        if k:
            d = holen(f"{API}/{urllib.parse.quote(k[0][0])}")
            print(f"--- Detail {k[0]}:\n{json.dumps(d, ensure_ascii=False)[:3000]}")
            print(f"--- KldB erkannt: {kldb_aus(d) if d else None!r}")
    print("--- Nachschlagen:", nachschlagen("Industriemechaniker/in"))


def main():
    if "--probe" in sys.argv:
        probe()
        return
    cache = laden_cache()
    heute = date.today()
    grenze = (heute - timedelta(days=WIEDERHOLEN_TAGE)).isoformat()
    offen = [b for b in berufe_nach_haeufigkeit()
             if b not in cache or (cache[b].get("quelle") != "KldB"
                                   and (cache[b].get("abgerufen") or "") < grenze)]
    neu = treffer = 0
    for b in offen:
        if neu >= MAX_NEU:
            print(f"Limit {MAX_NEU} erreicht, Rest im naechsten Lauf.")
            break
        try:
            code, bid, name = nachschlagen(b)
        except Gedrosselt:
            print("BERUFENET drosselt (429) - Abbruch, Rest im naechsten Lauf.")
            break
        except Exception as e:
            print(f"{b}: {e}", file=sys.stderr)
            continue
        neu += 1
        treffer += bool(code)
        cache[b] = {"beruf": b, "kldb": code, "berufenet_id": bid,
                    "berufenet_name": name, "abgerufen": heute.isoformat(),
                    "quelle": "KldB" if code else "offen"}
        if neu % 25 == 0:
            speichern(cache)
    speichern(cache)
    mit = sum(1 for r in cache.values() if r.get("quelle") == "KldB")
    print(f"KldB: {neu} abgefragt ({treffer} Treffer), {mit} von "
          f"{len(cache)} Berufen mit Code, {len(offen) - neu} noch offen.")


if __name__ == "__main__":
    main()
