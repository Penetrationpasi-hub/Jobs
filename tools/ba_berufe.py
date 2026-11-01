#!/usr/bin/env python3
"""
Arbeitslose und gemeldete Arbeitsstellen nach Berufssegmenten,
Agentur fuer Arbeit Waiblingen (= Rems-Murr-Kreis), Monatswerte.

Quelle: Arbeitsmarktreport der BA-Statistik (Excel, Blatt "Berufe"),
  https://statistik.arbeitsagentur.de/Statistikdaten/Detail/JJJJMM/ama/
  amr-amr/amr-671-0-JJJJMM-xlsx.xlsx
Kein Login noetig. Bereits geladene Monate werden uebersprungen; je Lauf
hoechstens BA_MAX_MONATE neue Monate (neueste zuerst), damit die BA nicht
mit "429 Too Many Requests" blockt. Bei 429 wird sofort aufgehoert, der
naechste Lauf macht weiter. Jeder Monat wird direkt gespeichert.

Output: data_historie/ba_berufe.csv  (monat;art;segment;anzahl)
"""

import csv
import io
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

BASE = Path(__file__).resolve().parent.parent
CSV_PFAD = BASE / "data_historie" / "ba_berufe.csv"
AGENTUR = os.environ.get("BA_AGENTUR", "671")          # 671 = Waiblingen
STARTMONAT = os.environ.get("BA_START", "2016-01")
URL = ("https://statistik.arbeitsagentur.de/Statistikdaten/Detail/{ym}/ama/"
       "amr-amr/amr-{ag}-0-{ym}-xlsx.xlsx?__blob=publicationFile&v=1")
UA = "arbeitsmarkt-historie/1.0 (privates Arbeitsmarkt-Monitoring)"
MAX_MONATE = int(os.environ.get("BA_MAX_MONATE", "24"))
PAUSE = float(os.environ.get("BA_PAUSE", "5"))


class Gedrosselt(Exception):
    """BA antwortet mit 429 - fuer diesen Lauf aufhoeren."""
FELDER = ["monat", "art", "segment", "anzahl"]


def monate(start: str):
    j, m = map(int, start.split("-"))
    heute = date.today()
    while (j, m) <= (heute.year, heute.month):
        yield f"{j:04d}-{m:02d}"
        m += 1
        if m > 12:
            j, m = j + 1, 1


def laden(ym: str) -> bytes | None:
    url = URL.format(ym=ym.replace("-", ""), ag=AGENTUR)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for versuch in range(2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code == 429:
                raise Gedrosselt()
            fehler = e
        except Exception as e:  # Netzwerk
            fehler = e
        time.sleep(3 * (versuch + 1))
    print(f"{ym}: Abruf fehlgeschlagen: {fehler}", file=sys.stderr)
    return None


def zahl(v):
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_berufe(daten: bytes):
    """Blatt 'Berufe' -> Liste (art, segment, anzahl).

    Gesucht wird die Tabelle unterhalb der Kopfzeile mit "Anzahl":
    Block "Arbeitslose" und Block "Gemeldete Arbeitsstellen", je mit
    Gesamtzeile und Zeilen je Berufssegment (erste Zahl = Anzahl).
    """
    wb = load_workbook(io.BytesIO(daten), read_only=True, data_only=True)
    ws = next((w for w in wb.worksheets if w.title.strip() == "Berufe"), None)
    if ws is None:
        return []
    ergebnis = []
    tabelle = False
    art = None
    for row in ws.iter_rows(values_only=True):
        zellen = [v for v in row if v not in (None, "")]
        if not zellen:
            continue
        texte = [str(v).strip() for v in zellen if isinstance(v, str)]
        if not tabelle:
            if any(t == "Anzahl" for t in texte):
                tabelle = True
            continue
        label = next((t for t in texte if t and t != "dar."), None)
        if label is None:
            continue
        if label.startswith("©"):
            break
        werte = [zahl(v) for v in zellen if not isinstance(v, str)]
        werte = [w for w in werte if w is not None]
        if not werte:
            continue
        if label.startswith("Arbeitslose"):
            art = "Arbeitslose"
            ergebnis.append((art, "Insgesamt", werte[0]))
        elif label.startswith("Gemeldete Arbeitsstellen"):
            art = "Gemeldete Arbeitsstellen"
            ergebnis.append((art, "Insgesamt", werte[0]))
        elif art:
            ergebnis.append((art, label, werte[0]))
    return ergebnis


def speichern(zeilen):
    zeilen.sort(key=lambda z: (z["monat"], z["art"], z["segment"]))
    tmp = CSV_PFAD.with_suffix(".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELDER, delimiter=";")
        w.writeheader()
        w.writerows(zeilen)
    tmp.replace(CSV_PFAD)


def main():
    CSV_PFAD.parent.mkdir(exist_ok=True)
    zeilen = []
    if CSV_PFAD.exists():
        with CSV_PFAD.open(newline="", encoding="utf-8") as f:
            zeilen = list(csv.DictReader(f, delimiter=";"))
    vorhanden = {z["monat"] for z in zeilen}
    neu = fehlend = 0
    offen = [ym for ym in monate(STARTMONAT) if ym not in vorhanden]
    for ym in reversed(offen):            # neueste zuerst
        if neu >= MAX_MONATE:
            print(f"Limit {MAX_MONATE} Monate erreicht, Rest im naechsten Lauf.")
            break
        try:
            daten = laden(ym)
        except Gedrosselt:
            print(f"{ym}: BA drosselt (429) - Abbruch, Rest im naechsten Lauf.")
            break
        if daten is None:
            fehlend += 1
            continue
        try:
            werte = parse_berufe(daten)
        except Exception as e:
            print(f"{ym}: Excel nicht lesbar: {e}", file=sys.stderr)
            continue
        if not werte:
            print(f"{ym}: Blatt 'Berufe' ohne erkennbare Tabelle",
                  file=sys.stderr)
            continue
        for art, seg, anz in werte:
            zeilen.append({"monat": ym, "art": art, "segment": seg,
                           "anzahl": int(anz) if float(anz).is_integer()
                           else anz})
        neu += 1
        speichern(zeilen)
        print(f"{ym}: {len(werte)} Werte")
        time.sleep(PAUSE)
    if zeilen:
        speichern(zeilen)
    print(f"BA-Berufe: {neu} Monate neu, {fehlend} nicht verfuegbar, "
          f"{len({z['monat'] for z in zeilen})} Monate gesamt.")


if __name__ == "__main__":
    main()
