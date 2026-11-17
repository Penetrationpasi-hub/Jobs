"""Tests fuer das gemeinsame Format (python -m pytest -q)."""
import csv

import collect_jobs as c
from orte import ANDERE, OHNE_ORT, kreis_von


def test_kreis_von_ba_und_freitext():
    assert kreis_von("Waiblingen, Rems") == "Rems-Murr-Kreis"
    assert kreis_von("71332 Waiblingen DE-BW") == "Rems-Murr-Kreis"
    assert kreis_von("Winnenden, DE, 71364") == "Rems-Murr-Kreis"
    assert kreis_von("70376 Stuttgart-Bad Cannstatt Baden-Württemberg DE") == "Stuttgart"
    # laengster Name gewinnt, "Murr" nur als ganzes Wort
    assert kreis_von("Weissach im Tal") == "Rems-Murr-Kreis"
    assert kreis_von("Weissach, Württemberg") == "Landkreis Böblingen"
    assert kreis_von("Kirchberg an der Murr") == "Rems-Murr-Kreis"
    assert kreis_von("Murr, Württemberg") == "Landkreis Ludwigsburg"
    assert kreis_von("Wien, AT") == ANDERE
    assert kreis_von("") == OHNE_ORT


def _ba(refnr, ag, titel, beruf, first, last, ort="Waiblingen, Rems"):
    return {"refnr": refnr, "region": "waiblingen_30km", "beruf": beruf,
            "titel": titel, "arbeitgeber": ag, "ort": ort,
            "first_seen": first, "last_seen": last}


def _sj(sid, ag, titel, first, last, aktiv="ja", ort="71332 Waiblingen DE"):
    return {"id": sid, "quelle": "x", "arbeitgeber": ag, "titel": titel,
            "ort": ort, "url": "https://example.org/" + sid,
            "veroeffentlicht": "", "first_seen": first, "last_seen": last,
            "aktiv": aktiv}


def test_baue_stellen_alle(tmp_path, monkeypatch):
    monkeypatch.setattr(c, "DATA", str(tmp_path))
    log = [
        _ba("1", "Muster Maschinenbau GmbH", "Industriemechaniker (m/w/d)",
            "Industriemechaniker/in", "2026-11-01", "2026-11-17"),
        # gleicher Titel, aber laengst beendet -> kein Partner
        _ba("2", "Muster Maschinenbau GmbH", "Elektroniker (m/w/d)",
            "Elektroniker/in", "2026-07-01", "2026-07-10"),
        _ba("3", "Andere Firma AG", "Pflegefachkraft (m/w/d)",
            "Pflegefachmann/-frau", "2026-11-01", "2026-11-17"),
    ]
    sj = [
        _sj("a", "Muster Maschinenbau", "Industriemechaniker (w/m/d)",
            "2026-11-08", "2026-11-08"),
        _sj("b", "Muster Maschinenbau", "Elektroniker (m/w/d)",
            "2026-11-08", "2026-11-08"),
        _sj("c", "Klinik XY", "Pflegefachkraft (m/w/d)",
            "2026-11-08", "2026-11-08", aktiv="nein"),
    ]
    alle = c.baue_stellen_alle(log, sj, "2026-11-17")
    by = {r["stellen_id"]: r for r in alle}
    assert len(alle) == 5                      # 3 BA + 3 SJ - 1 Doppelte
    assert by["BA:1"]["herkunft"] == "beide"
    assert by["BA:1"]["scrapjobs_id"] == "a"
    assert by["BA:1"]["offen"] == "ja"
    assert by["BA:2"]["herkunft"] == "BA" and by["BA:2"]["offen"] == "nein"
    assert by["SJ:b"]["herkunft"] == "Karriereseite"
    assert by["SJ:b"]["beruf"] == "Elektroniker/in"      # ueber Titel
    assert by["SJ:b"]["beruf_quelle"] == "Titel-Abgleich"
    assert by["SJ:c"]["offen"] == "nein"
    assert by["SJ:c"]["branche"] == "Gesundheit & Pflege"
    assert all(r["kreis"] == "Rems-Murr-Kreis" for r in alle)
    with open(tmp_path / "stellen_alle.csv", encoding="utf-8") as fh:
        assert len(list(csv.DictReader(fh))) == 5
