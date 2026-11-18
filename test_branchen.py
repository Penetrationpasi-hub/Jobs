"""Tests fuer die Branchenzuordnung (python -m pytest -q)."""
import csv
import os
import sys

import branchen as B

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
import kldb_zuordnung as K  # noqa: E402


def test_tabellen_vollstaendig():
    # 37 Berufshauptgruppen, jede genau einem der 14 Segmente zugeordnet
    assert len(B.HAUPTGRUPPEN) == 37
    assert {seg for _n, seg in B.HAUPTGRUPPEN.values()} == set(B.SEGMENTE)
    assert len(B.SEGMENTE) == 14
    assert {seg[:2] for seg in B.SEGMENTE} == set(B.SEKTOREN)
    assert set(B.SEGMENT_KURZ) >= set(B.SEGMENTE)


def test_segmentnamen_wie_ba_statistik():
    pfad = os.path.join(os.path.dirname(__file__), "data_historie",
                        "ba_berufe.csv")
    if not os.path.exists(pfad):
        return
    with open(pfad, encoding="utf-8-sig", newline="") as fh:
        namen = {r["segment"] for r in csv.DictReader(fh, delimiter=";")}
    namen -= {"Insgesamt", "Keine Angabe"}
    assert namen == set(B.SEGMENTE.values())


def test_stichwort_rueckfall():
    erwartet = {
        "Industriemechaniker/in": "25",
        "Ingenieur/in - Maschinenbau": "25",
        "Kraftfahrzeugmechatroniker/in - Personenkraftwagentechnik": "25",
        "Mechatroniker/in": "26",
        "Elektroniker/in - Energie- und Gebäudetechnik": "26",
        "Mechatroniker/in - Kältetechnik": "34",
        "Zerspanungsmechaniker/in": "24",
        "CNC-Fachkraft/NC-Anwendungsfachmann/-frau": "24",
        "Tischler/in": "22",
        "Friseur/in": "82",
        "Altenpfleger/in": "82",
        "Gesundheits- und Krankenpfleger/in": "81",
        "Heilerziehungspfleger/in": "83",
        "Gebäudereiniger/in": "54",
        "Fahrzeugpfleger/in": "54",
        "Gabelstaplerfahrer/in": "52",
        "Fahrlehrer/in": "84",
        "Fachkraft - Lagerlogistik": "51",
        "Fachverkäufer/in - Lebensmittelhandwerk (Bäckerei)": "62",
        "Bäcker/in": "29",
        "Koch/Köchin": "29",
        "Hochbauingenieur/in": "31",
        "Gärtner/in - Garten- und Landschaftsbau": "12",
        "Personalentwickler/in": "71",
        "ERP-Systembetreuer/in": "43",
        "Cyber-Security-Consultant": "43",
        "Sicherheitsmitarbeiter/in": "53",
        "Bankkaufmann/-frau": "72",
        "Kundenberater/in (Bank, Sparkasse)": "72",
        "Bankettleiter/in": "63",
        "Verwaltungswirt/in / Verwaltungsbetriebswirt/in": "73",
        "Einsatzleiter/in (Sicherheitsgewerbe)": "53",
    }
    falsch = {b: (B.hauptgruppe_per_stichwort(b), hg)
              for b, hg in erwartet.items()
              if B.hauptgruppe_per_stichwort(b) != hg}
    assert not falsch


def test_kldb_cache_und_handkorrektur(tmp_path, monkeypatch):
    cache = tmp_path / "beruf_kldb.csv"
    hand = tmp_path / "beruf_kldb_manuell.csv"
    cache.write_text("beruf,kldb,berufenet_id,berufenet_name,quelle,abgerufen\n"
                     "Montierer/in,B 24202,1,Montierer/in,KldB,2026-11-18\n"
                     "Gruppen-, Teamleiter/in,,,,offen,2026-11-18\n",
                     encoding="utf-8")
    hand.write_text("beruf,kldb\nFriseur/in,82312\n", encoding="utf-8")
    monkeypatch.setattr(B, "KLDB_DATEI", str(cache))
    monkeypatch.setattr(B, "KLDB_MANUELL", str(hand))
    B.lade_kldb(neu=True)
    try:
        e = B.einordnung("Montierer/in")
        assert (e.hauptgruppe, e.segment, e.kldb, e.quelle) == \
            ("24", "S12", "24202", "KldB")        # KldB schlaegt Stichwort (25)
        assert B.einordnung("Friseur/in").quelle == "Hand"
        e = B.einordnung("Gruppen-, Teamleiter/in")   # offen im Cache
        assert e.segment == "" and e.segment_name == B.SONSTIGE
        assert B.einordnung("Koch/Köchin").quelle == "Stichwort"
        assert B.branche_von_beruf("Koch/Köchin") == \
            "Lebensmittel- und Gastgewerbeberufe"
    finally:
        monkeypatch.undo()
        B.lade_kldb(neu=True)


def test_berufenet_antwort_auswerten():
    suche = {"_embedded": {"berufSucheList": [
        {"id": 58761, "kurzBezeichnungNeutral": "Industriemechaniker/in"},
        {"id": 1, "kurzBezeichnungNeutral": "Industriemeister/in - Metall"}]}}
    assert ("58761", "Industriemechaniker/in") in K.kandidaten(suche)
    assert K.kldb_aus({"x": {"kldb2010-Code": "B 25102"}}) == "25102"
    assert K.kldb_aus({"text": "Systematik B 26302 KldB"}) == "26302"
    assert K.kldb_aus({"kldb2010-Code": ""}) == ""
    assert list(K.suchbegriffe("Elektroniker/in - Betriebstechnik"))[1] == \
        "Elektroniker"


def test_nachschlagen_ablauf(monkeypatch):
    aufrufe = []

    def fake_holen(url):
        aufrufe.append(url)
        if "/berufe/58761" in url:
            return {"id": 58761, "kldb2010-Code": "B 25102"}
        if "suchwoerter" in url:
            return {"_embedded": {"berufSucheList": [
                {"id": 99, "kurzBezeichnungNeutral": "Industriemechaniker/in - Feingeraetebau"},
                {"id": 58761, "kurzBezeichnungNeutral": "Industriemechaniker/in"}]}}
        return None

    monkeypatch.setattr(K, "holen", fake_holen)
    monkeypatch.setattr(K, "PAUSE", 0)
    assert K.nachschlagen("Industriemechaniker/in") == \
        ("25102", "58761", "Industriemechaniker/in")
    # kein exakter Name -> nichts uebernehmen, aber besten Namen merken
    code, bid, name = K.nachschlagen("Unbekannter Beruf/in")
    assert code == "" and bid == ""
