"""Geografische Abgrenzung, Archivschutz und Umstellung der Zeitreihen."""
import csv
import math

import pytest
from openpyxl import load_workbook

import collect_jobs as c
from test_stellen_alle import _ba, _sj
from umkreis import (REGION, ZENTRUM, entfernung, filter_stellen,
                     im_umkreis, pruefe_ort, zeitreihen)


@pytest.mark.parametrize("ort", [
    "Waiblingen, Rems", "Schwäbisch Gmünd", "Stuttgart", "Urbach, Rems",
    "71332 Waiblingen DE-BW", "Winnenden, DE, 71364",
    "Winterbach bei Schorndorf, Württ.", "Rommelshausen DE",
])
def test_innerhalb(ort):
    assert im_umkreis(ort)


@pytest.mark.parametrize("ort", [
    "Heidenheim an der Brenz", "Aalen, Württemberg", "Oberkochen", "Berlin",
    "87487 Wiggensbach Bayern DE", "", "Remote Deutschland", "unbekannter Ort",
    "Mason, 45039, IL", "71332 Waiblingen DE / 10117 Berlin DE",
    "Waiblingen / Heidenheim an der Brenz",
])
def test_nicht_innerhalb(ort):
    assert not im_umkreis(ort)


def test_radius_grenze():
    for km in (49.99, 50, 50.01):
        lat = ZENTRUM[0] + math.degrees(km / 6371.0088)
        assert entfernung(lat, ZENTRUM[1]) == pytest.approx(km)
    assert 35 < pruefe_ort("Schwäbisch Gmünd")[1] < 40
    assert pruefe_ort("Heidenheim an der Brenz")[1] > 50


def test_abgleich_filtert_vor_deduplizierung(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DATA", str(tmp_path))
    log = [_ba("1", "Muster GmbH", "Koch", "Koch/Köchin", "2026-11-01",
               "2026-11-21", ort="Heidenheim an der Brenz")]
    sj = [_sj("a", "Muster GmbH", "Koch", "2026-11-01", "2026-11-21")]
    result = c.baue_stellen_alle(log, sj, "2026-11-21")
    assert [(r["stellen_id"], r["herkunft"]) for r in result] == [("SJ:a", "Karriereseite")]
    assert len(log) == len(sj) == 1


def test_zeitreihe_alt_neu_und_leerer_tag():
    log = [_ba("1", "Muster", "Koch", "Koch/Köchin", "2026-11-01", "2026-11-23")]
    snaps = [
        {"datum": "2026-11-21", "region": "ostalbkreis", "stellen_gesamt": 999},
        {"datum": "2026-11-21", "region": "waiblingen_30km", "stellen_gesamt": 999},
        {"datum": "2026-11-22", "region": REGION},
        {"datum": "2026-11-23", "region": REGION},
    ]
    observation = {"datum": "2026-11-22", **log[0]}
    berufe, result = zeitreihen(log, snaps, [observation, observation])
    assert [r["stellen_gesamt"] for r in result] == [1, 1, 0]
    assert result[0]["methode"].startswith("Rekonstruktion")
    assert result[1]["methode"] == "Tagesbeobachtungen"
    assert len(berufe) == 2


def test_beobachtungen_ersetzen_nur_aktuellen_tag(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DATA_DIR", tmp_path)
    job = _ba("1", "Firma", "Koch", "Koch/Köchin", "2026-11-01", "2026-11-22")
    c.update_beobachtungen("2026-11-21", {"1": job})
    c.update_beobachtungen("2026-11-22", {"1": job})
    c.update_beobachtungen("2026-11-22", {})
    with (tmp_path / "jobs_beobachtungen.csv").open(encoding="utf-8") as f:
        assert [r["datum"] for r in csv.DictReader(f)] == ["2026-11-21"]


@pytest.mark.parametrize("leer", [False, True])
def test_auswertung_alle_blaetter_und_rohdaten(tmp_path, monkeypatch, leer):
    monkeypatch.setattr(c, "DATA", str(tmp_path))
    monkeypatch.setattr(c, "OUT", str(tmp_path / "test.xlsx"))
    log = [
        _ba("1", "Lokale Firma", "Koch", "Koch/Köchin", "2026-11-01", "2026-11-21"),
        _ba("2", "Auswaertige Firma", "Koch", "Koch/Köchin", "2026-11-01", "2026-11-21",
            ort="Heidenheim an der Brenz"),
    ][1 if leer else 0:]
    source = {
        "jobs_log.csv": log,
        "snapshots.csv": [{"datum": "2026-11-21", "region": "ostalbkreis", "stellen_gesamt": 999}],
        "berufe.csv": [{"datum": "2026-11-21", "region": "ostalbkreis", "beruf": "Koch/Köchin", "anzahl": 999}],
    }
    for filename, rows in source.items():
        with (tmp_path / filename).open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    before = {name: (tmp_path / name).read_bytes() for name in source}
    assert c.build_excel() == 0
    assert before == {name: (tmp_path / name).read_bytes() for name in source}
    wb = load_workbook(tmp_path / "test.xlsx")
    assert wb["Zusammenfassung"]["B5"].value == (0 if leer else 1)
    assert wb["Zeitreihe"]["B2"].value == (0 if leer else 1)
    assert wb["Branchen"]["B4"].value == (0 if leer else 1)
    for ws in wb:
        assert not any(cell.value == "Auswaertige Firma" for row in ws for cell in row)


def test_suche_nur_waiblingen():
    assert c.REGIONS == {REGION: {"wo": "Waiblingen", "umkreis": 50}}


def test_sammlung_behaelt_archiv_und_importiert_nur_lokale(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DATA_DIR", tmp_path)
    monkeypatch.setattr(c, "fetch_arbeitslose", lambda: None)
    old = _ba("alt", "Alte Firma", "Koch", "Koch/Köchin", "2026-07-01",
              "2026-11-21", ort="Heidenheim an der Brenz")
    c.update_jobs_log(tmp_path / "jobs_log.csv", "2026-11-21", {"alt": old})
    monkeypatch.setattr(c, "fetch_region", lambda params: ([
        {"refnr": "lokal", "beruf": "Koch/Köchin", "arbeitsort": {"ort": "Waiblingen, Rems"}},
        {"refnr": "fern", "beruf": "Koch/Köchin", "arbeitsort": {"ort": "Heidenheim an der Brenz"}},
    ], 2))
    monkeypatch.setattr(c, "lade_scrapjobs_json", lambda: {
        "aktualisiert": c.date.today().isoformat(), "stellen": [
            {"id": "lokal", "location": "71332 Waiblingen DE"},
            {"id": "fern", "location": "Heidenheim an der Brenz"},
        ],
    })
    c.main()
    for name, field, expected in (
        ("jobs_log.csv", "refnr", {"alt", "lokal"}),
        ("jobs_beobachtungen.csv", "refnr", {"lokal"}),
        ("scrapjobs_log.csv", "id", {"lokal"}),
        ("snapshots.csv", "region", {REGION}),
    ):
        with (tmp_path / name).open(encoding="utf-8") as f:
            assert {r[field] for r in csv.DictReader(f)} == expected


def test_wiederholungslauf_verwendet_beobachtungen_fuer_offen():
    row = {"last_seen": "2026-11-22", "_offen": False}
    assert not c.ba_ist_offen(row, "2026-11-22")
