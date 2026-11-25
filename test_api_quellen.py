"""Tests fuer die Boersen-Stichprobe (python -m pytest -q), ohne Netz."""
import csv
from datetime import date, timedelta

import api_quellen as a
import collect_jobs as c


def _stelle(i, titel="Industriemechaniker (m/w/d)", firma="Muster GmbH", ort="71332 Waiblingen"):
    return {"id": f"X:{i}", "quelle": "Test", "portal": "Test", "arbeitgeber": firma,
            "titel": titel, "ort": ort, "url": "https://example.org/" + str(i),
            "veroeffentlicht": ""}


def test_rotation_deckt_alle_segmente_ab():
    tage = [a.tages_plan(a.START + timedelta(days=n)) for n in range(14)]
    assert {s for s, _ in tage} == set(a.SUCHBEGRIFFE)
    # naechster Durchlauf: gleiche Segmente, naechster Begriff
    assert a.tages_plan(a.START)[0] == a.tages_plan(a.START + timedelta(days=14))[0]
    assert a.tages_plan(a.START)[1] != a.tages_plan(a.START + timedelta(days=14))[1]


def test_sammle_filtert_umkreis_schreibt_log_und_sperrt_doppelte_abfrage(tmp_path):
    aufrufe = []

    def quelle(b, r):
        aufrufe.append(b)
        return [_stelle(1), _stelle(2, ort="Hamburg")], 1, 0.02

    heute = date(2026, 12, 1).isoformat()
    log = a.sammle(heute, tmp_path, {"Test": quelle}, budget=0.25)
    assert [r["id"] for r in log] == ["X:1"]
    a.sammle(heute, tmp_path, {"Test": quelle}, budget=0.25)
    assert len(aufrufe) == 1                        # kein zweiter (bezahlter) Abruf
    morgen = (date(2026, 12, 1) + timedelta(days=1)).isoformat()
    log = a.sammle(morgen, tmp_path, {"Test": quelle}, budget=0.25)
    assert log[0]["first_seen"] == heute and log[0]["last_seen"] == morgen
    laeufe = list(csv.DictReader(open(tmp_path / a.LAEUFE, encoding="utf-8")))
    assert [(r["datum"], r["im_umkreis"], r["neu"]) for r in laeufe] == [(heute, "1", "1"), (morgen, "1", "0")]


def test_budget_und_fehler_stoppen_nicht_die_anderen_quellen(tmp_path):
    def teuer(b, r):
        assert r == 0.25
        return [], 1, 0.25

    def kaputt(b, r):
        raise a.QuellenFehler("HTTP 500")

    def spaet(b, r):
        assert r == 0
        raise a.QuellenFehler("Budget aufgebraucht")

    a.sammle("2026-12-01", tmp_path, {"A": teuer, "B": kaputt, "C": spaet}, budget=0.25)
    status = {r["quelle"]: r["status"] for r in csv.DictReader(open(tmp_path / a.LAEUFE, encoding="utf-8"))}
    assert status == {"A": "ok", "B": "fehler: HTTP 500", "C": "uebersprungen: Budget aufgebraucht"}


def test_ohne_zugang_wird_uebersprungen(monkeypatch):
    for v in ("ADZUNA_APP_ID", "ADZUNA_APP_KEY", "SERPAPI_API_KEY", "APIFY_API_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    for f in (lambda: a.adzuna("x"), lambda: a.google_jobs("x", 1), lambda: a.apify("x", 1)):
        try:
            f()
            assert False
        except a.QuellenFehler as e:
            assert str(e) == "kein Zugang"


def test_adzuna_und_google_mapping(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "i")
    monkeypatch.setenv("ADZUNA_APP_KEY", "k")
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    adz = {"results": [{"id": "9", "title": "Koch", "company": {"display_name": "Gasthaus"},
                        "location": {"display_name": "Waiblingen"}, "redirect_url": "https://x", "created": "2026-12-01T00:00:00Z"}]}
    s, n, k = a.adzuna("Koch", http=lambda url, *a_: adz)
    assert (s[0]["id"], s[0]["arbeitgeber"], s[0]["veroeffentlicht"], n, k) == ("ADZUNA:9", "Gasthaus", "2026-12-01", 1, 0.0)
    goo = {"jobs_results": [{"title": "Koch", "company_name": "Gasthaus", "location": "Waiblingen",
                             "job_id": "abc", "via": "über LinkedIn", "apply_options": [{"link": "https://y"}]}]}
    s, n, k = a.google_jobs("Koch", 1.0, http=lambda url, *a_: goo)
    assert (s[0]["portal"], s[0]["url"], n, k) == ("LinkedIn", "https://y", 1, a.SERPAPI_USD)


def test_google_beachtet_restbudget(monkeypatch):
    monkeypatch.setenv("SERPAPI_API_KEY", "k")
    seite = {"jobs_results": [], "serpapi_pagination": {"next_page_token": "t"}}
    _, n, k = a.google_jobs("x", a.SERPAPI_USD * 2.5, http=lambda url, *a_: seite)
    assert n == 2


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
