#!/usr/bin/env python3
"""Diagnose: GENESIS-Katalog und BA-Statistikseiten auflisten.

Laeuft nur in GitHub Actions (manuell), schreibt alles ins Log.
  python tools/erkunden.py katalog 13111* 13211*
  python tools/erkunden.py links <url> [filter]
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request

BASE = (os.environ.get("GENESIS_BASE", "").strip()
        or "https://www.regionalstatistik.de/genesisws/rest/2020").rstrip("/")
UA = "arbeitsmarkt-historie/1.0 (privates Arbeitsmarkt-Monitoring)"


def genesis(endpoint, params):
    user = os.environ.get("GENESIS_USER", "").strip()
    pw = os.environ.get("GENESIS_PASS", "").strip()
    req = urllib.request.Request(
        f"{BASE}/{endpoint}",
        data=urllib.parse.urlencode(params).encode(), method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "username": user, "password": pw, "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def katalog(muster):
    for m in muster:
        print(f"\n===== Katalog {m}")
        try:
            d = genesis("catalogue/tables", {"selection": m, "area": "all",
                                             "pagelength": 2500,
                                             "language": "de"})
        except Exception as e:
            print(f"Fehler: {e}")
            continue
        for t in d.get("List") or []:
            text = " ".join((t.get("Content") or "").split())
            print(f"{t.get('Code')} | {text}")


def links(url, filt=""):
    print(f"\n===== Links {url} (Filter: {filt or '-'})")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"Fehler: {e}")
        return
    gesehen = set()
    for href in re.findall(r'href="([^"]+)"', html):
        voll = urllib.parse.urljoin(url, href.replace("&amp;", "&"))
        if filt and not re.search(filt, voll, re.I):
            continue
        if voll not in gesehen:
            gesehen.add(voll)
            print(voll)


def xlsx(url, zeilen=25):
    """Excel laden und je Blatt die ersten Zeilen ausgeben."""
    import io
    from openpyxl import load_workbook
    print(f"\n===== XLSX {url}")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            daten = r.read()
    except Exception as e:
        print(f"Fehler: {e}")
        return
    wb = load_workbook(io.BytesIO(daten), read_only=True, data_only=True)
    for ws in wb.worksheets:
        print(f"\n--- Blatt '{ws.title}' ({ws.max_row} x {ws.max_column})")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= zeilen:
                break
            werte = [str(v)[:40] for v in row if v not in (None, "")]
            if werte:
                print(f"{i + 1:3}: " + " | ".join(werte[:14]))


if __name__ == "__main__":
    modus, *rest = sys.argv[1:] or ["katalog"]
    if modus == "katalog":
        katalog(rest or ["13111*", "13211*"])
    elif modus == "xlsx":
        for u in rest:
            xlsx(u)
    elif modus == "links":
        links(rest[0], rest[1] if len(rest) > 1 else "")
