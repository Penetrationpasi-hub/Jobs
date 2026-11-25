"""Tests fuer die Boersen-Stichprobe (python -m pytest -q), ohne Netz."""
import csv

import api_quellen as a
import collect_jobs as c


def _stelle(i, titel="Industriemechaniker (m/w/d)", firma="Muster GmbH",
            ort="71332 Waiblingen", quelle="Adzuna"):
    return {"id": f"X:{i}", "quelle": quelle, "portal": "LinkedIn",
            "arbeitgeber": firma, "titel": titel, "ort": ort,
            "url": "https://example.org/" + str(i), "veroeffentlicht": ""}


def _tag(datum, stellen, status="ok", kosten=0.02):
    return {"datum": datum, "segment": "S13", "suchbegriff": "Mechatroniker",
            "laeufe": [{"datum": datum, "quelle": "Adzuna", "segment": "S13",
                        "suchbegriff": "Mechatroniker", "abfragen": 1,
                        "treffer_roh": len(stellen), "kosten_usd": kosten,
                        "status": status}],
            "stellen": stellen}


def _csv(pfad):
    return list(csv.DictReader(open(pfad, encoding="utf-8")))


def test_sammle_filtert_umkreis_und_schreibt_log(tmp_path):
    tage = [_tag("2026-12-01", [_stelle(1), _stelle(2, ort="Hamburg")])]
    log = a.sammle("2026-12-02", tmp_path, export=lambda seit: tage)
    assert [r["id"] for r in log] == ["X:1"]
    lauf = _csv(tmp_path / a.LAEUFE)[0]
    assert (lauf["datum"], lauf["treffer_roh"], lauf["im_umkreis"], lauf["neu"]) == ("2026-12-01", "2", "1", "1")
    assert _csv(tmp_path / a.LOG)[0]["first_seen"] == "2026-12-01"


def test_zweiter_import_gleicher_tage_aendert_nichts_und_fortschreibung(tmp_path):
    erster = [_tag("2026-12-01", [_stelle(1)])]
    a.sammle("2026-12-05", tmp_path, export=lambda seit: erster)
    seiten = []

    def export(seit):
        seiten.append(seit)
        return erster + [_tag("2026-12-02", [_stelle(1), _stelle(3)])]

    a.sammle("2026-12-05", tmp_path, export=export)
    assert seiten == ["2026-12-01"]                 # holt ab dem letzten bekannten Tag
    log = {r["id"]: r for r in _csv(tmp_path / a.LOG)}
    assert (log["X:1"]["first_seen"], log["X:1"]["last_seen"]) == ("2026-12-01", "2026-12-02")
    assert log["X:3"]["first_seen"] == "2026-12-02"
    laeufe = _csv(tmp_path / a.LAEUFE)
    assert [(r["datum"], r["neu"]) for r in laeufe] == [("2026-12-01", "1"), ("2026-12-02", "1")]


def test_zukunft_und_ausfall_brechen_nicht_ab(tmp_path):
    a.sammle("2026-12-01", tmp_path, export=lambda seit: [_tag("2026-12-09", [_stelle(1)])])
    assert _csv(tmp_path / a.LOG) == []

    def kaputt(seit):
        raise a.QuellenFehler("HTTP 502")

    assert a.sammle("2026-12-01", tmp_path, export=kaputt) == []


def test_ohne_url_wird_uebersprungen(monkeypatch):
    monkeypatch.delenv("BOERSEN_URL", raising=False)
    try:
        a.hole_export("2026-12-01")
        assert False
    except a.QuellenFehler as e:
        assert "BOERSEN_URL" in str(e)


def test_boersen_zeilen_erkennt_ba_dubletten():
    ba = [{"refnr": "1", "region": "r", "beruf": "Industriemechaniker/in", "titel": "Industriemechaniker (m/w/d)",
           "arbeitgeber": "Muster GmbH", "ort": "Waiblingen, Rems", "first_seen": "2026-11-01", "last_seen": "2026-11-20"}]
    api = [{**_stelle(1), "suchbegriff": "x", "segment": "S13", "first_seen": "2026-12-01", "last_seen": "2026-12-01"},
           {**_stelle(2, titel="Schweisser", firma="Andere AG"), "suchbegriff": "x", "segment": "S12",
            "first_seen": "2026-12-01", "last_seen": "2026-12-01"},
           {**_stelle(3, ort="Hamburg"), "suchbegriff": "x", "segment": "S13",
            "first_seen": "2026-12-01", "last_seen": "2026-12-01"}]
    z = c.boersen_zeilen(api, ba)
    assert [(r["id"], r["auch_bei_ba"]) for r in z] == [("X:1", "ja"), ("X:2", "nein")]
