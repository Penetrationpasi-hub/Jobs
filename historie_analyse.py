"""
Blatt "Analyse" fuer arbeitsmarkt_historie.xlsx.

Verdichtet die Rohreihen aus data_historie/ zu Aussagen:
Kernaussagen (automatisch formuliert), Kreisvergleich, Arbeitslosenquote,
Beschaeftigungsindex, Strukturwandel nach Wirtschaftszweigen, Alterung
der Belegschaften und Engpassberufe (BA, Agentur Waiblingen).

Alle Werte werden bei jedem Lauf aus den CSVs neu berechnet.
"""

import csv
import math
from pathlib import Path

from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill

ARIAL = "Arial"
HEAD_FONT = Font(name=ARIAL, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", start_color="1D3C6E")
FOKUS_FILL = PatternFill("solid", start_color="E8EEF7")
TITEL = Font(name=ARIAL, bold=True, size=14)
ABSCHNITT = Font(name=ARIAL, bold=True, size=12, color="1D3C6E")
KLEIN = Font(name=ARIAL, italic=True, size=9, color="555555")

QUOTE = "Arbeitslosenquote bez. auf alle zivile Erwerbsp."
AL = "Arbeitslose"
FOKUS = "08119"          # Rems-Murr-Kreis = Agentur Waiblingen

# Aggregate der WZ 2008, die nicht in den Strukturvergleich gehoeren
WZ_AGGREGATE = {"Insgesamt", "Dienstleistungsbereiche (G-U)",
                "Produzierendes Gewerbe (B-F)",
                "Produzierendes Gewerbe ohne Baugewerbe (B-E)"}
WZ_C = "Verarbeitendes Gewerbe (C)"
WZ_BE = "Produzierendes Gewerbe ohne Baugewerbe (B-E)"
WZ_BDE = "Bergbau, Energie, Wasser, Entsorgung (B, D, E)"
WZ_KURZ = {
    "Land- und Forstwirtschaft, Fischerei (A)": "Land-/Forstwirtschaft (A)",
    WZ_BDE: "Energie, Wasser, Bergbau (B,D,E)",
    WZ_C: "Verarbeitendes Gewerbe (C)",
    "Baugewerbe (F)": "Baugewerbe (F)",
    "Handel, Gastgewerbe, Verkehr (G-I)": "Handel, Gastgew., Verkehr (G-I)",
    "Information und Kommunikation (J)": "Information/Kommunikation (J)",
    "Erbringung von Finanz- und Versicherungsdienstleistungen (K)":
        "Finanzen/Versicherungen (K)",
    "Grundstücks- und Wohnungswesen (L)": "Grundstücke/Wohnen (L)",
    "Erbringung von freiberuflichen, wissenschaftlichen, tech. und sonst. "
    "wirtsch. Dienstleistungen": "Unternehmensdienstl. inkl. Zeitarbeit (M,N)",
    "Öff. Verwaltung, Verteidig.; Sozialvers., Erziehung und Unterricht, "
    "Gesundheits- und Sozialwesen": "Öff. Dienst, Bildung, Gesundheit (O-Q)",
    "Kunst, Unterhaltung und Erholung, sonstige Dienstl., Private "
    "Haushalte, Exterritoriale Org.": "Sonstige Dienstleistungen (R-U)",
}


# ---------------- kleine Helfer ---------------------------------------

def _index(rows, merkmal=None):
    """(ags, jahr, dim) -> wert fuer Jahreswerte."""
    out = {}
    for r in rows:
        if r["monat"] or r["wert"] is None:
            continue
        if merkmal and r["merkmal"] != merkmal:
            continue
        out[(r["ags"], r["jahr"], r["dim"])] = r["wert"]
    return out


def _jahre(idx, dim="Insgesamt"):
    return sorted({j for (_, j, d) in idx if d == dim})


def _pct(a, b):
    return a / b - 1 if a is not None and b else None


def _de(x, nachkomma=0):
    """Zahl deutsch formatiert fuer Fliesstext."""
    if x is None:
        return "–"
    s = f"{x:,.{nachkomma}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def _pp(x):
    """Prozentveraenderung mit Vorzeichen; kleine Werte mit Nachkomma."""
    nk = 1 if abs(x) < 0.05 else 0
    return f"{'+' if x >= 0 else '−'}{_de(abs(x) * 100, nk)} %"


def _abs(x):
    return f"{'+' if x >= 0 else '−'}{_de(abs(x))}"


def _kopf(ws, zeile, werte, spalte=1):
    for k, v in enumerate(werte):
        z = ws.cell(row=zeile, column=spalte + k, value=v)
        z.font = HEAD_FONT
        z.fill = HEAD_FILL
        z.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[zeile].height = 42


def _linie(titel, y_fmt="#,##0", hoehe=9, breite=17):
    ch = LineChart()
    ch.title = titel
    ch.height, ch.width = hoehe, breite
    ch.y_axis.number_format = y_fmt
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    ch.legend.position = "b"
    return ch


def _text(ws, zeile, text, font=None, breite_zeichen=125, bis_spalte=8):
    ws.merge_cells(start_row=zeile, start_column=1, end_row=zeile,
                   end_column=bis_spalte)
    z = ws.cell(row=zeile, column=1, value=text)
    z.alignment = Alignment(wrap_text=True, vertical="top")
    if font:
        z.font = font
    ws.row_dimensions[zeile].height = 15 * max(
        1, math.ceil(len(text) / breite_zeichen))


def _ba_berufe(pfad: Path):
    if not pfad.exists():
        return None
    with pfad.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if not rows:
        return None
    werte = {(r["monat"], r["art"], r["segment"]): float(r["anzahl"])
             for r in rows}
    monate = sorted({r["monat"] for r in rows})
    return werte, monate


# ---------------- Blatt -----------------------------------------------

def analyse_blatt(wb, lade, kreise, data_dir: Path, position=1):
    alo_roh = lade("arbeitslose")
    alo_q = _index([r for r in alo_roh if r["merkmal"] == QUOTE])
    alo_n = _index([r for r in alo_roh if r["merkmal"] == AL])
    bes = _index(lade("beschaeftigte"))
    wz = _index(lade("besch_branchen"))
    alt = _index(lade("besch_alter"))
    if not (alo_n or bes):
        return None

    ags_liste = list(kreise)
    # Fokuskreis zuerst
    if FOKUS in ags_liste:
        ags_liste.remove(FOKUS)
        ags_liste.insert(0, FOKUS)
    namen = [kreise[a] for a in ags_liste]

    ws = wb.create_sheet("Analyse", position)
    ws.sheet_view.showGridLines = False
    ws["A1"] = "Analyse: Arbeitsmarkt Rems-Murr, Stuttgart, Ostalb"
    ws["A1"].font = TITEL
    _text(ws, 2, ("Automatisch aus den amtlichen Jahreswerten berechnet "
                  "(Regionaldatenbank, BA). Kreisdaten, keine "
                  "50-km-Auswertung. Fokus: Rems-Murr-Kreis = Agentur "
                  "Waiblingen."), KLEIN)

    j_al = _jahre(alo_n)
    j_al_neu = j_al[-1] if j_al else None
    j_b = _jahre(bes)
    j_b_neu = j_b[-1] if j_b else None
    j_wz = _jahre(wz)
    j_wz_neu = j_wz[-1] if j_wz else None
    vgl = 2019                      # letztes Jahr vor Corona

    # ---------- Kennzahlen je Kreis
    kz = {}
    for a in ags_liste:
        d = {}
        if j_al_neu:
            d["al"] = alo_n.get((a, j_al_neu, "Insgesamt"))
            d["q"] = alo_q.get((a, j_al_neu, "Insgesamt"))
            qs = [(alo_q.get((a, j, "Insgesamt")), j) for j in j_al
                  if alo_q.get((a, j, "Insgesamt")) is not None]
            if qs:
                d["q_min"], d["q_min_j"] = min(qs)
            d["al_vgl"] = alo_n.get((a, vgl, "Insgesamt"))
            d["al_d"] = _pct(d["al"], d["al_vgl"])
            for key, dim in (("lz", "langzeitarbeitslos"),
                             ("ausl", "ausländisch"),
                             ("u25", "15 bis unter 25 Jahre"),
                             ("ue55", "55 bis unter 65 Jahre")):
                w = alo_n.get((a, j_al_neu, dim))
                d[key] = w / d["al"] if w is not None and d["al"] else None
            d["q_ausl"] = alo_q.get((a, j_al_neu, "ausländisch"))
        if j_b_neu:
            d["svb"] = bes.get((a, j_b_neu, "Insgesamt"))
            d["svb_d"] = _pct(d["svb"], bes.get((a, vgl, "Insgesamt")))
            d["svb_d1"] = _pct(d["svb"], bes.get((a, j_b_neu - 1,
                                                  "Insgesamt")))
        if j_wz_neu:
            ges = wz.get((a, j_wz_neu, "Insgesamt"))
            c = wz.get((a, j_wz_neu, WZ_C))
            d["c_ant"] = c / ges if c and ges else None
            d["c_d"] = _pct(c, wz.get((a, vgl, WZ_C)))
            d["c_abs"] = (c - wz[(a, vgl, WZ_C)]
                          if c and (a, vgl, WZ_C) in wz else None)
        if alt:
            ja = _jahre(alt)[-1]
            t = alt.get((a, ja, "Insgesamt"))
            s60 = sum(alt.get((a, ja, g)) or 0 for g in (
                "60 bis unter 65 Jahre", "65 Jahre und mehr"))
            s50 = s60 + (alt.get((a, ja, "50 bis unter 60 Jahre")) or 0)
            d["ant50"] = s50 / t if t else None
            d["ant60"] = s60 / t if t else None
            d["alt_j"] = ja
        kz[a] = d

    # ---------- Kernaussagen
    z = 4
    ws.cell(row=z, column=1, value="Kernaussagen").font = ABSCHNITT
    z += 1
    aussagen = []
    f = kz.get(FOKUS, {})
    if f.get("q") is not None and f.get("al_d") is not None:
        aussagen.append(
            ("Arbeitslosigkeit steigt" if f["al_d"] > 0.05 else
             "Arbeitslosigkeit sinkt" if f["al_d"] < -0.05 else
             "Arbeitslosigkeit kaum verändert")
            + f" seit {vgl}: Im Rems-Murr-Kreis "
            f"{_de(f['al'])} Arbeitslose im Jahresdurchschnitt {j_al_neu} "
            f"({_pp(f['al_d'])} gegenüber {vgl}), Quote {_de(f['q'], 1)} % "
            f"nach dem Tiefstand von {_de(f['q_min'], 1)} % ({f['q_min_j']}). "
            "Stuttgart "
            f"{_de(kz[ags_liste[1]].get('q'), 1) if len(ags_liste) > 1 else '–'} %, "
            "Ostalbkreis "
            f"{_de(kz[ags_liste[2]].get('q'), 1) if len(ags_liste) > 2 else '–'} %.")
    if f.get("svb_d") is not None:
        aussagen.append(
            ("Beschäftigung stagniert" if abs(f["svb_d"]) < 0.03 else
             "Beschäftigung wächst" if f["svb_d"] > 0 else
             "Beschäftigung sinkt")
            + f": {_de(f['svb'])} "
            f"SV-Beschäftigte am Arbeitsort ({j_b_neu}), {_pp(f['svb_d'])} "
            f"seit {vgl}, {_pp(f['svb_d1'])} zum Vorjahr."
            + (" Mehr Arbeitslose bei kaum veränderter Beschäftigung heißt: "
               "Der Markt nimmt kaum zusätzliche Kräfte auf."
               if abs(f["svb_d"]) < 0.03 and (f.get("al_d") or 0) > 0.05
               else ""))
    if f.get("c_d") is not None:
        plus = sorted(
            ((wz.get((FOKUS, j_wz_neu, d)) or 0)
             - (wz.get((FOKUS, vgl, d)) or 0), WZ_KURZ[d])
            for d in WZ_KURZ if d in {k[2] for k in wz} and d != WZ_C)
        top = ", ".join(f"{n} ({_abs(v)})" for v, n in plus[::-1][:2]
                        if v > 0)
        aussagen.append(
            ("Industrie schrumpft" if f["c_d"] < 0 else "Industrie wächst")
            + f" im Rems-Murr-Kreis: Verarbeitendes Gewerbe "
            f"{_pp(f['c_d'])} seit {vgl} ({_abs(f['c_abs'])} Beschäftigte), "
            f"Anteil an allen Beschäftigten {_de(f['c_ant'] * 100, 0)} %."
            + (f" Die größten Zuwächse: {top}." if top else ""))
    if f.get("lz") is not None:
        aussagen.append(
            f"Struktur der Arbeitslosigkeit (Rems-Murr {j_al_neu}): "
            f"{_de(f['ausl'] * 100, 0)} % ausländische Staatsangehörige "
            f"(Quote {_de(f.get('q_ausl'), 1)} %), "
            f"{_de(f['lz'] * 100, 0)} % langzeitarbeitslos, "
            f"{_de(f['ue55'] * 100, 0)} % sind 55–64 Jahre alt, "
            f"{_de(f['u25'] * 100, 0)} % unter 25.")
    if f.get("ant60") is not None:
        aussagen.append(
            f"Belegschaften altern: {_de(f['ant50'] * 100, 0)} % der "
            f"Beschäftigten im Rems-Murr-Kreis sind 50+ und "
            f"{_de(f['ant60'] * 100, 0)} % bereits 60+ ({f['alt_j']})"
            + (" – der höchste Wert der drei Kreise"
               if f["ant60"] >= max(kz[a].get("ant60") or 0
                                    for a in ags_liste) else "")
            + ". Dieser Ersatzbedarf entsteht "
            "unabhängig von der Konjunktur in den nächsten 5–10 Jahren.")
    ba = _ba_berufe(data_dir / "ba_berufe.csv")
    engpass = []
    if ba:
        werte, monate = ba
        letzt = monate[-1]
        for (mo, art, sg), v in werte.items():
            if mo != letzt or art != AL or sg == "Insgesamt":
                continue
            st = werte.get((letzt, "Gemeldete Arbeitsstellen", sg))
            if st:
                engpass.append((v / st, sg, v, st))
        engpass.sort()
        if len(engpass) >= 4:
            knapp = ", ".join(f"{s} ({_de(r, 1)})" for r, s, _, _
                              in engpass[:3])
            viel = ", ".join(f"{s} ({_de(r, 1)})" for r, s, _, _
                             in engpass[-2:])
            aussagen.append(
                f"Engpässe trotz steigender Arbeitslosigkeit (Agentur "
                f"Waiblingen, {letzt}, Arbeitslose je gemeldeter Stelle): "
                f"am knappsten {knapp}; die meisten Bewerber je Stelle: "
                f"{viel}.")
    for i, s in enumerate(aussagen, start=1):
        _text(ws, z, f"{i}. {s}")
        z += 1

    # ---------- Kreisvergleich
    z += 1
    ws.cell(row=z, column=1, value="Kreisvergleich").font = ABSCHNITT
    z += 1
    _kopf(ws, z, ["Kennzahl"] + namen)
    z += 1
    zeilen = [
        (f"Arbeitslose {j_al_neu} (Jahresdurchschnitt)", "al", "#,##0"),
        (f"Arbeitslosenquote {j_al_neu}", "q", '0.0" %"'),
        ("Tiefste Quote seit 2008", "q_min", '0.0" %"'),
        ("… im Jahr", "q_min_j", "0"),
        (f"Arbeitslose: Veränderung seit {vgl}", "al_d", "+0%;-0%"),
        ("Anteil Langzeitarbeitslose", "lz", "0%"),
        ("Anteil ausländische Arbeitslose", "ausl", "0%"),
        ("Anteil 55–64-Jährige an Arbeitslosen", "ue55", "0%"),
        ("Anteil unter 25-Jährige an Arbeitslosen", "u25", "0%"),
        (f"SV-Beschäftigte {j_b_neu}", "svb", "#,##0"),
        (f"SV-Beschäftigte: Veränderung seit {vgl}", "svb_d", "+0.0%;-0.0%"),
        ("SV-Beschäftigte: Veränderung zum Vorjahr", "svb_d1",
         "+0.0%;-0.0%"),
        ("Anteil Verarbeitendes Gewerbe", "c_ant", "0%"),
        (f"Verarbeitendes Gewerbe: Veränderung seit {vgl}", "c_d",
         "+0.0%;-0.0%"),
        ("Anteil Beschäftigte 50+", "ant50", "0%"),
        ("Anteil Beschäftigte 60+", "ant60", "0%"),
    ]
    for name, key, fmt in zeilen:
        ws.cell(row=z, column=1, value=name)
        for k, a in enumerate(ags_liste):
            c = ws.cell(row=z, column=2 + k, value=kz[a].get(key))
            c.number_format = fmt
            if a == FOKUS:
                c.fill = FOKUS_FILL
        z += 1

    # ---------- Zeitreihen: Quote, Beschaeftigungsindex, Alterung
    def reihe(titel, jahre, wert_fn, fmt, y_fmt, notiz=None, y_min=None):
        nonlocal z
        z += 1
        ws.cell(row=z, column=1, value=titel).font = ABSCHNITT
        if notiz:
            ws.cell(row=z + 1, column=1, value=notiz).font = KLEIN
            z += 1
        z += 1
        kopf = z
        _kopf(ws, kopf, ["Jahr"] + namen)
        for i, j in enumerate(jahre, start=kopf + 1):
            ws.cell(row=i, column=1, value=j)
            for k, a in enumerate(ags_liste):
                ws.cell(row=i, column=2 + k,
                        value=wert_fn(a, j)).number_format = fmt
        ende = kopf + len(jahre)
        ch = _linie(titel, y_fmt)
        if y_min is not None:
            ch.y_axis.scaling.min = y_min
        ch.add_data(Reference(ws, min_col=2, max_col=1 + len(ags_liste),
                              min_row=kopf, max_row=ende),
                    titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=kopf + 1,
                                    max_row=ende))
        ws.add_chart(ch, f"F{kopf - 1}")
        z = max(ende, kopf + 18) + 1

    if alo_q:
        reihe("Arbeitslosenquote (alle zivilen Erwerbspersonen)",
              _jahre(alo_q),
              lambda a, j: alo_q.get((a, j, "Insgesamt")),
              '0.0" %"', '0.0" %"')
    if bes and j_b:
        basis = 2015 if 2015 in j_b else j_b[0]
        reihe(f"SV-Beschäftigte, Index {basis} = 100", j_b,
              lambda a, j: (round(bes[(a, j, "Insgesamt")]
                                  / bes[(a, basis, "Insgesamt")] * 100, 1)
                            if (a, j, "Insgesamt") in bes
                            and (a, basis, "Insgesamt") in bes else None),
              "0.0", "0", "Macht das Wachstum der unterschiedlich großen "
              "Kreise vergleichbar.", y_min=80)
    if alt:
        def ant60(a, j):
            t = alt.get((a, j, "Insgesamt"))
            s = sum(alt.get((a, j, g)) or 0 for g in (
                "60 bis unter 65 Jahre", "65 Jahre und mehr"))
            return s / t if t else None
        reihe("Anteil Beschäftigte 60+ (Ersatzbedarf)", _jahre(alt),
              ant60, "0.0%", "0%",
              "Wer heute 60+ ist, scheidet in den nächsten Jahren aus.")

    # ---------- Strukturwandel nach Wirtschaftszweigen
    if wz and j_wz_neu and vgl in j_wz:
        z += 1
        ws.cell(row=z, column=1,
                value=f"Strukturwandel: SV-Beschäftigte nach "
                      f"Wirtschaftszweig, {vgl} → {j_wz_neu}").font = ABSCHNITT
        ws.cell(row=z + 1, column=1, value=(
            "Absolute Veränderung je Kreis; sortiert nach Rems-Murr. "
            "B,D,E = Produzierendes Gewerbe ohne Bau minus Verarbeitendes "
            "Gewerbe. M,N enthält die Zeitarbeit.")).font = KLEIN
        z += 2

        def wzwert(a, j, dim):
            if dim == WZ_BDE:
                be, c = wz.get((a, j, WZ_BE)), wz.get((a, j, WZ_C))
                return be - c if be is not None and c is not None else None
            return wz.get((a, j, dim))

        dims = [d for d in WZ_KURZ if d == WZ_BDE
                or any(k[2] == d for k in wz)]
        dims = [d for d in dims if d not in WZ_AGGREGATE]

        def delta(a, d):
            w0, w1 = wzwert(a, vgl, d), wzwert(a, j_wz_neu, d)
            return w1 - w0 if w0 is not None and w1 is not None else None
        dims.sort(key=lambda d: -(delta(FOKUS, d) or 0))
        kopf = z
        spalten = ["Wirtschaftszweig"]
        for n in namen:
            spalten += [f"{n} Δ", f"{n} Δ %"]
        spalten += [f"Anteil {j_wz_neu} ({namen[0]})"]
        _kopf(ws, kopf, spalten)
        ges_fokus = wz.get((FOKUS, j_wz_neu, "Insgesamt"))
        for i, d in enumerate(dims, start=kopf + 1):
            ws.cell(row=i, column=1, value=WZ_KURZ.get(d, d))
            for k, a in enumerate(ags_liste):
                dl = delta(a, d)
                c1 = ws.cell(row=i, column=2 + 2 * k, value=dl)
                c1.number_format = "+#,##0;-#,##0"
                c2 = ws.cell(row=i, column=3 + 2 * k, value=_pct(
                    wzwert(a, j_wz_neu, d), wzwert(a, vgl, d)))
                c2.number_format = "+0%;-0%"
                if a == FOKUS:
                    c1.fill = c2.fill = FOKUS_FILL
            w = wzwert(FOKUS, j_wz_neu, d)
            ws.cell(row=i, column=2 + 2 * len(ags_liste),
                    value=w / ges_fokus if w and ges_fokus else None
                    ).number_format = "0%"
        ende = kopf + len(dims)
        bc = BarChart()
        bc.type = "bar"
        bc.title = (f"{namen[0]}: Veränderung der Beschäftigten "
                    f"{vgl}–{j_wz_neu}")
        bc.height, bc.width = 10, 17
        bc.legend = None
        bc.y_axis.number_format = "+#,##0;-#,##0"
        bc.x_axis.delete = False
        bc.y_axis.delete = False
        # Beschriftung links neben der Achse, Reihenfolge wie die Tabelle
        bc.x_axis.tickLblPos = "low"
        bc.x_axis.scaling.orientation = "maxMin"
        bc.add_data(Reference(ws, min_col=2, min_row=kopf, max_row=ende),
                    titles_from_data=True)
        bc.set_categories(Reference(ws, min_col=1, min_row=kopf + 1,
                                    max_row=ende))
        ws.add_chart(bc, f"A{ende + 2}")
        z = ende + 23

    # ---------- Engpassberufe
    if engpass:
        z += 1
        ws.cell(row=z, column=1, value=(
            f"Arbeitslose je gemeldeter Stelle nach Berufssegment "
            f"(Agentur Waiblingen, {ba[1][-1]})")).font = ABSCHNITT
        ws.cell(row=z + 1, column=1, value=(
            "Unter 3 = eher Fachkräfteengpass, über 8 = viele Bewerber "
            "je Stelle. Gemeldete Stellen erfassen nur einen Teil aller "
            "offenen Stellen.")).font = KLEIN
        z += 2
        kopf = z
        _kopf(ws, kopf, ["Berufssegment", "Arbeitslose",
                         "Gemeldete Stellen", "Arbeitslose je Stelle",
                         "Einordnung"])
        for i, (r, sg, v, st) in enumerate(engpass, start=kopf + 1):
            ws.cell(row=i, column=1, value=sg)
            ws.cell(row=i, column=2, value=v).number_format = "#,##0"
            ws.cell(row=i, column=3, value=st).number_format = "#,##0"
            ws.cell(row=i, column=4, value=round(r, 1)).number_format = "0.0"
            ws.cell(row=i, column=5, value=(
                "Engpass" if r < 3 else "ausgeglichen" if r <= 8
                else "Überangebot an Bewerbern"))
        z = kopf + len(engpass) + 1

    # Spaltenbreiten (werden in build_excel nicht ueberschrieben)
    ws.column_dimensions["A"].width = 44
    for k in range(2, 9):
        ws.column_dimensions[chr(64 + k)].width = 15
    ws._feste_breiten = True
    return ws
