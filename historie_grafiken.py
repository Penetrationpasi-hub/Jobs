"""
Blatt "Grafiken" fuer arbeitsmarkt_historie.xlsx.

Aufbau wie das Blatt "Branchen" in arbeitsmarkt_auswertung.xlsx: links
die Datenbloecke, rechts daneben je ein nummeriertes Diagramm.
Gewinner/Verlierer gruen/rot, Mix-Entwicklung als 100-%-Flaeche,
Indexlinien mit angepasster Achse. Fokus ist der Rems-Murr-Kreis
(Agentur Waiblingen), Vergleich mit Stuttgart und Ostalbkreis.

Alles wird bei jedem Lauf aus data_historie/ neu berechnet.
"""

import csv
import re
from pathlib import Path

from openpyxl.chart import AreaChart, BarChart, LineChart, Reference
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.marker import DataPoint
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from historie_analyse import (AL, FOKUS, QUOTE, WZ_BDE, WZ_BE, WZ_C,
                              WZ_KURZ, _index, _jahre)

ARIAL = "Arial"
HEAD_FONT = Font(name=ARIAL, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", start_color="1D3C6E")
TITEL = Font(name=ARIAL, bold=True, size=14)
ABSCHNITT = Font(name=ARIAL, bold=True, size=11, color="1D3C6E")
KLEIN = Font(name=ARIAL, italic=True, size=9, color="555555")
GRUEN, ROT, GRAU = "63BE7B", "F8696B", "BFBFBF"

DIAGRAMM_SPALTE = 15          # Spalte O: rechts neben den Datenbloecken
BLOCK_ZEILEN = 24             # Hoehe eines Diagramms in Zeilen (+ Luft)
VGL = 2019                    # letztes Jahr vor Corona


# ---------------- Diagramm-Helfer (wie collect_jobs.py) ---------------

def _achsen(ch, y_titel=None, y_fmt="#,##0"):
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    if y_titel:
        ch.y_axis.title = y_titel
    if y_fmt:
        ch.y_axis.number_format = y_fmt
    ch.y_axis.majorGridlines = ChartLines()
    ch.legend.position = "b"


def _linie(titel, y_titel=None, y_fmt="#,##0"):
    ch = LineChart()
    ch.title = titel
    ch.height, ch.width = 11, 20
    _achsen(ch, y_titel, y_fmt)
    return ch


def _balken(titel, y_titel, n, y_fmt="#,##0"):
    ch = BarChart()
    ch.type = "bar"
    ch.grouping = "clustered"
    ch.gapWidth = 60
    ch.title = titel
    ch.height, ch.width = max(8.0, min(14.0, 2 + 0.75 * n)), 20
    _achsen(ch, y_titel, y_fmt)
    # Rang 1 oben, Wertachse unten, Namen links aussen
    ch.x_axis.scaling.orientation = "maxMin"
    ch.y_axis.crosses = "max"
    ch.x_axis.tickLblPos = "low"
    return ch


def _gruen_rot(ch, werte, umgekehrt=False):
    """Positive Balken gruen, negative rot (umgekehrt: niedrig = rot)."""
    ser = ch.series[0]
    ser.invertIfNegative = False
    ser.graphicalProperties.solidFill = GRUEN
    for i, w in enumerate(werte):
        schlecht = (w is not None and w < 0) if not umgekehrt else \
            (w is not None and w > 0)
        if schlecht:
            dp = DataPoint(idx=i)
            dp.graphicalProperties.solidFill = ROT
            ser.dPt.append(dp)


def _y_bereich(ch, werte, schritt=10):
    werte = [w for w in werte if w is not None]
    if werte:
        ch.y_axis.scaling.min = (int(min(werte)) // schritt) * schritt
        ch.y_axis.scaling.max = (int(max(werte)) // schritt + 1) * schritt


# ---------------- Blatt -----------------------------------------------

class _Blatt:
    """Schreibt Datenbloecke untereinander und haengt je Block ein
    Diagramm rechts daneben an."""

    def __init__(self, ws):
        self.ws = ws
        self.z = 4

    def block(self, titel, kopf, zeilen, notiz=None, formate=None):
        ws = self.ws
        ws.cell(row=self.z, column=1, value=titel).font = ABSCHNITT
        if notiz:
            ws.cell(row=self.z + 1, column=1, value=notiz).font = KLEIN
        k = self.z + 2
        for i, t in enumerate(kopf, start=1):
            c = ws.cell(row=k, column=i, value=t)
            c.font, c.fill = HEAD_FONT, HEAD_FILL
            c.alignment = Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[k].height = 45
        for r, zeile in enumerate(zeilen, start=k + 1):
            for i, v in enumerate(zeile, start=1):
                c = ws.cell(row=r, column=i, value=v)
                if formate and i > 1:
                    c.number_format = formate[min(i - 2, len(formate) - 1)]
        self.kopf, self.ende, self.start = k, k + len(zeilen), self.z
        return self

    def ref(self, spalte_von, spalte_bis=None, mit_titel=True):
        return Reference(self.ws, min_col=spalte_von,
                         max_col=spalte_bis or spalte_von,
                         min_row=self.kopf if mit_titel else self.kopf + 1,
                         max_row=self.ende)

    def kategorien(self):
        return self.ref(1, mit_titel=False)

    def diagramm(self, ch):
        self.ws.add_chart(ch, f"{get_column_letter(DIAGRAMM_SPALTE)}"
                              f"{self.start}")
        self.z = max(self.ende, self.start + BLOCK_ZEILEN) + 2


def _ba_berufe(pfad: Path):
    if not pfad.exists():
        return None
    with pfad.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    if not rows:
        return None
    werte = {(r["monat"], r["art"], r["segment"]): float(r["anzahl"])
             for r in rows}
    return werte, sorted({r["monat"] for r in rows})


def _alter_von(label):
    low = label.lower()
    z = [int(x) for x in re.findall(r"\d+", low)]
    if not z:
        return None
    if low.startswith("unter"):
        return 0
    return z[0]


def grafiken_blatt(wb, lade, kreise, data_dir: Path, position=2):
    alo_roh = lade("arbeitslose")
    alo_n = _index([r for r in alo_roh if r["merkmal"] == AL])
    alo_q = _index([r for r in alo_roh if r["merkmal"] == QUOTE])
    bes = _index(lade("beschaeftigte"))
    wz = _index(lade("besch_branchen"))
    alt = _index(lade("besch_alter"))
    bev = _index(lade("bevoelkerung"))
    if not (alo_n or bes):
        return None

    fk = kreise.get(FOKUS, FOKUS)
    ags_liste = [FOKUS] + [a for a in kreise if a != FOKUS]
    namen = [kreise[a] for a in ags_liste]

    ws = wb.create_sheet("Grafiken", position)
    ws.sheet_view.showGridLines = False
    ws["A1"] = f"Grafiken: {fk} im Vergleich"
    ws["A1"].font = TITEL
    ws["A2"] = ("Datenbloecke links, Diagramme rechts (ab Spalte "
                f"{get_column_letter(DIAGRAMM_SPALTE)}). Amtliche "
                "Kreisdaten, keine 50-km-Auswertung.")
    ws["A2"].font = KLEIN
    b = _Blatt(ws)
    nr = 0

    def titel(t):
        nonlocal nr
        nr += 1
        return f"{nr}  {t}"

    # ---- 1  Schere: Arbeitslose vs. Beschaeftigte (Index)
    jahre = [j for j in _jahre(alo_n) if (FOKUS, j, "Insgesamt") in bes]
    if VGL in jahre:
        a0 = alo_n[(FOKUS, VGL, "Insgesamt")]
        b0 = bes[(FOKUS, VGL, "Insgesamt")]
        zeilen = [[j,
                   round(alo_n[(FOKUS, j, "Insgesamt")] / a0 * 100, 1),
                   round(bes[(FOKUS, j, "Insgesamt")] / b0 * 100, 1)]
                  for j in jahre]
        b.block(titel(f"Arbeitslose und Beschäftigte, {fk} "
                      f"(Index {VGL} = 100)"),
                ["Jahr", "Arbeitslose", "SV-Beschäftigte"], zeilen,
                "Öffnet sich die Schere, finden Arbeitslose trotz stabiler "
                "Beschäftigung schwerer zurück.", ["0.0"])
        ch = _linie(ws.cell(row=b.start, column=1).value, "Index", "0")
        _y_bereich(ch, [v for z in zeilen for v in z[1:]], 10)
        ch.add_data(b.ref(2, 3), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

    # ---- 2  Quote nach Personengruppen
    gruppen = [("Insgesamt", "Insgesamt"), ("Männer", "Männer"),
               ("Frauen", "Frauen"), ("ausländisch", "Ausländer/innen"),
               ("15 bis unter 25 Jahre", "15–24 Jahre")]
    gruppen = [(d, n) for d, n in gruppen
               if any(k[0] == FOKUS and k[2] == d for k in alo_q)]
    if len(gruppen) > 1:
        jq = _jahre(alo_q)
        zeilen = [[j] + [alo_q.get((FOKUS, j, d)) for d, _ in gruppen]
                  for j in jq]
        b.block(titel(f"Arbeitslosenquote nach Personengruppen, {fk}"),
                ["Jahr"] + [n for _, n in gruppen], zeilen,
                "Quote bezogen auf alle zivilen Erwerbspersonen, in %.",
                ['0.0" %"'])
        ch = _linie(ws.cell(row=b.start, column=1).value, "Quote in %",
                    '0" %"')
        ch.add_data(b.ref(2, 1 + len(gruppen)), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

    # ---- 3  Wer ist arbeitslos? Personengruppen absolut
    grp = [("Insgesamt", "Insgesamt"), ("ausländisch", "Ausländer/innen"),
           ("langzeitarbeitslos", "Langzeitarbeitslose"),
           ("55 bis unter 65 Jahre", "55–64 Jahre"),
           ("15 bis unter 25 Jahre", "15–24 Jahre"),
           ("schwerbehindert", "Schwerbehinderte")]
    grp = [(d, n) for d, n in grp
           if any(k[0] == FOKUS and k[2] == d for k in alo_n)]
    if len(grp) > 1:
        ja = _jahre(alo_n)
        zeilen = [[j] + [alo_n.get((FOKUS, j, d)) for d, _ in grp]
                  for j in ja]
        b.block(titel(f"Arbeitslose nach Personengruppen, {fk}"),
                ["Jahr"] + [n for _, n in grp], zeilen,
                "Gruppen überschneiden sich (z. B. ausländisch und "
                "langzeitarbeitslos), deshalb nicht addieren.", ["#,##0"])
        ch = _linie(ws.cell(row=b.start, column=1).value, "Arbeitslose")
        ch.add_data(b.ref(2, 1 + len(grp)), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

    # ---- Wirtschaftszweige (ohne Aggregate, B,D,E berechnet)
    def wzwert(a, j, d):
        if d == WZ_BDE:
            be, c = wz.get((a, j, WZ_BE)), wz.get((a, j, WZ_C))
            return be - c if be is not None and c is not None else None
        return wz.get((a, j, d))

    wz_dims = [d for d in WZ_KURZ
               if d == WZ_BDE or any(k[2] == d for k in wz)]
    jw = _jahre(wz)
    if wz_dims and jw and VGL in jw:
        jn = jw[-1]

        # ---- 4  Gewinner/Verlierer absolut
        delta = {d: (wzwert(FOKUS, jn, d) or 0) - (wzwert(FOKUS, VGL, d)
                                                    or 0) for d in wz_dims}
        sort = sorted(wz_dims, key=lambda d: -delta[d])
        zeilen = [[WZ_KURZ[d], delta[d]] for d in sort]
        b.block(titel(f"Gewinner und Verlierer: Beschäftigte nach "
                      f"Wirtschaftszweig, {fk} ({VGL}–{jn})"),
                ["Wirtschaftszweig", f"Δ Beschäftigte {VGL}–{jn}"], zeilen,
                None, ["+#,##0;-#,##0"])
        ch = _balken(ws.cell(row=b.start, column=1).value, "Beschäftigte",
                     len(zeilen), "+#,##0;-#,##0")
        ch.add_data(b.ref(2), titles_from_data=True)
        ch.set_categories(b.kategorien())
        ch.legend = None
        _gruen_rot(ch, [z[1] for z in zeilen])
        b.diagramm(ch)

        # ---- 5  Wachstum je Zweig im Kreisvergleich (%)
        zeilen = []
        for d in sort:
            zeile = [WZ_KURZ[d]]
            for a in ags_liste:
                w0, w1 = wzwert(a, VGL, d), wzwert(a, jn, d)
                zeile.append(w1 / w0 - 1 if w0 and w1 is not None else None)
            zeilen.append(zeile)
        b.block(titel(f"Veränderung je Wirtschaftszweig im Kreisvergleich "
                      f"({VGL}–{jn}, in %)"),
                ["Wirtschaftszweig"] + namen, zeilen,
                "Gleiche Reihenfolge wie Grafik davor.", ["+0%;-0%"])
        ch = _balken(ws.cell(row=b.start, column=1).value, "Veränderung",
                     len(zeilen) * 1.6, "+0%;-0%")
        ch.add_data(b.ref(2, 1 + len(ags_liste)), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

        # ---- 6  Branchenmix im Zeitverlauf (100 %)
        mix_dims = sorted(wz_dims, key=lambda d: -(wzwert(FOKUS, jn, d)
                                                    or 0))
        zeilen = [[j] + [wzwert(FOKUS, j, d) for d in mix_dims] for j in jw]
        b.block(titel(f"Branchenmix der Beschäftigten im Zeitverlauf, {fk}"),
                ["Jahr"] + [WZ_KURZ[d] for d in mix_dims], zeilen, None,
                ["#,##0"])
        ch = AreaChart()
        ch.grouping = "percentStacked"
        ch.title = ws.cell(row=b.start, column=1).value
        ch.height, ch.width = 12, 20
        _achsen(ch, "Anteil", "0%")
        ch.legend.position = "r"
        ch.add_data(b.ref(2, 1 + len(mix_dims)), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

        # ---- 7  Industrie im Kreisvergleich (Index)
        if all((a, VGL, WZ_C) in wz for a in ags_liste):
            zeilen = [[j] + [round(wz[(a, j, WZ_C)] / wz[(a, VGL, WZ_C)]
                                   * 100, 1)
                             if (a, j, WZ_C) in wz else None
                             for a in ags_liste] for j in jw]
            b.block(titel(f"Verarbeitendes Gewerbe im Kreisvergleich "
                          f"(Index {VGL} = 100)"),
                    ["Jahr"] + namen, zeilen,
                    "Industrie-Beschäftigte am Arbeitsort.", ["0.0"])
            ch = _linie(ws.cell(row=b.start, column=1).value, "Index", "0")
            _y_bereich(ch, [v for z in zeilen for v in z[1:]], 10)
            ch.add_data(b.ref(2, 1 + len(ags_liste)), titles_from_data=True)
            ch.set_categories(b.kategorien())
            b.diagramm(ch)

    # ---- 8  Altersstruktur der Beschaeftigten (100 %)
    if alt:
        ja = _jahre(alt)
        bands = sorted({k[2] for k in alt if k[0] == FOKUS
                        and k[2] != "Insgesamt"},
                       key=lambda d: _alter_von(d) or 0)
        zeilen = [[j] + [alt.get((FOKUS, j, d)) for d in bands] for j in ja]
        b.block(titel(f"Altersstruktur der Beschäftigten, {fk}"),
                ["Jahr"] + bands, zeilen,
                "Die oberen Schichten (50+) wachsen: Ersatzbedarf der "
                "nächsten Jahre.", ["#,##0"])
        ch = AreaChart()
        ch.grouping = "percentStacked"
        ch.title = ws.cell(row=b.start, column=1).value
        ch.height, ch.width = 12, 20
        _achsen(ch, "Anteil", "0%")
        ch.legend.position = "r"
        ch.add_data(b.ref(2, 1 + len(bands)), titles_from_data=True)
        ch.set_categories(b.kategorien())
        b.diagramm(ch)

    # ---- 9  Bevoelkerung nach Alter: erstes vs. letztes Jahr
    if bev:
        jb = _jahre(bev)
        j0, j1 = jb[0], jb[-1]
        bands = {}
        for (a, j, d), w in bev.items():
            if a != FOKUS or d == "Insgesamt" or j not in (j0, j1):
                continue
            von = _alter_von(d)
            if von is None:
                continue
            g = min(von // 5 * 5, 85)
            bands[(g, j)] = bands.get((g, j), 0) + w
        gs = sorted({g for g, _ in bands})
        zeilen = [[f"{g}–{g + 4}" if g < 85 else "85+",
                   bands.get((g, j0)), bands.get((g, j1))] for g in gs]
        b.block(titel(f"Bevölkerung nach Alter, {fk}: {j0} und {j1}"),
                ["Alter", str(j0), str(j1)], zeilen,
                "Der Babyboomer-Berg wandert Richtung Rente; dahinter "
                "rücken schwächere Jahrgänge nach.", ["#,##0"])
        ch = BarChart()
        ch.type = "col"
        ch.grouping = "clustered"
        ch.gapWidth = 40
        ch.title = ws.cell(row=b.start, column=1).value
        ch.height, ch.width = 11, 20
        _achsen(ch, "Personen")
        ch.add_data(b.ref(2, 3), titles_from_data=True)
        ch.set_categories(b.kategorien())
        ch.series[0].graphicalProperties.solidFill = GRAU
        ch.series[1].graphicalProperties.solidFill = "1D3C6E"
        b.diagramm(ch)

    # ---- 10/11  BA: Engpass und Veraenderung je Berufssegment
    ba = _ba_berufe(data_dir / "ba_berufe.csv")
    if ba:
        werte, monate = ba
        letzt = monate[-1]
        jj, mm = map(int, letzt.split("-"))
        vorj = f"{jj - 1:04d}-{mm:02d}"
        segs = sorted({s for (_, _, s) in werte
                       if s not in ("Insgesamt", "Keine Angabe")})
        eng = []
        for s in segs:
            al = werte.get((letzt, AL, s))
            st = werte.get((letzt, "Gemeldete Arbeitsstellen", s))
            if al is not None and st:
                eng.append([s, round(al / st, 1)])
        eng.sort(key=lambda z: z[1])
        if eng:
            b.block(titel(f"Engpass: Arbeitslose je gemeldeter Stelle "
                          f"(Agentur Waiblingen, {letzt}) – niedrig = "
                          "Fachkräfte knapp"),
                    ["Berufssegment", "Arbeitslose je Stelle"], eng,
                    "Rot: unter 3 (Engpass), grau: 3–8, grün: über 8 "
                    "(viele Bewerber).", ["0.0"])
            ch = _balken(ws.cell(row=b.start, column=1).value,
                         "Arbeitslose je Stelle", len(eng), "0.0")
            ch.add_data(b.ref(2), titles_from_data=True)
            ch.set_categories(b.kategorien())
            ch.legend = None
            ser = ch.series[0]
            ser.graphicalProperties.solidFill = GRAU
            for i, (_, r) in enumerate(eng):
                if r < 3 or r > 8:
                    dp = DataPoint(idx=i)
                    dp.graphicalProperties.solidFill = ROT if r < 3 \
                        else GRUEN
                    ser.dPt.append(dp)
            b.diagramm(ch)

        ver = []
        for s in segs:
            a1, a0 = werte.get((letzt, AL, s)), werte.get((vorj, AL, s))
            if a1 is not None and a0:
                ver.append([s, a1 / a0 - 1])
        ver.sort(key=lambda z: z[1])
        if ver:
            b.block(titel(f"Arbeitslose je Berufssegment: Veränderung zum "
                          f"Vorjahr ({vorj} → {letzt})"),
                    ["Berufssegment", "Veränderung"], ver,
                    "Grün: weniger Arbeitslose, rot: mehr.", ["+0%;-0%"])
            ch = _balken(ws.cell(row=b.start, column=1).value,
                         "Veränderung", len(ver), "+0%;-0%")
            ch.add_data(b.ref(2), titles_from_data=True)
            ch.set_categories(b.kategorien())
            ch.legend = None
            _gruen_rot(ch, [z[1] for z in ver], umgekehrt=True)
            b.diagramm(ch)

    ws.column_dimensions["A"].width = 44
    for k in range(2, DIAGRAMM_SPALTE):
        ws.column_dimensions[get_column_letter(k)].width = 12
    ws._feste_breiten = True
    return ws
