"""
Arbeitsmarkt-Auswertung: baut aus den CSVs des Sammlers (collect_jobs.py)
die Datei arbeitsmarkt_auswertung.xlsx. Laeuft nach dem Sammler im selben
Workflow und schreibt die Excel bei jedem Lauf komplett neu aus dem
Gesamtbestand. Kein API-Zugriff, keine Zugangsdaten noetig.

Blaetter:
  Zusammenfassung   Stand, Umfang, Hinweise
  Zeitreihe         Stellen gesamt je Region und Tag (mit Diagramm)
  Berufe-Zeitreihe  Top-20-Berufe im Zeitverlauf
  Aktuell           Stellen je Beruf heute, je Region, Veraenderung 7/30 Tage
  Standzeit         wie lange bleiben Stellen online, je Beruf
  Arbeitgeber       Top-Arbeitgeber nach offenen Stellen
  AL-Relation       Arbeitslose je Stelle (Arbeitslosenzahlen manuell
                    aus der BA-Statistik eintragen, blaue Spalte)
  Log               Rohdaten aller je gesehenen Stellen
"""

import csv
import os
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
OUT = os.path.join(BASE, "arbeitsmarkt_auswertung.xlsx")

REGION_NAMEN = {
    "waiblingen_15km": "Waiblingen 15 km",
    "rems-murr-kreis": "Rems-Murr-Kreis",
    "ostalbkreis": "Ostalbkreis",
}

ARIAL = "Arial"
HEAD_FONT = Font(name=ARIAL, bold=True, color="FFFFFF")
HEAD_FILL = PatternFill("solid", start_color="1D3C6E")
INPUT_FONT = Font(name=ARIAL, color="0000FF")
DATUM_FMT = "DD.MM.YYYY"


def read_csv(name):
    path = os.path.join(DATA, name)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def as_date(s):
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def style_header(ws, ncols):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEAD_FONT
        cell.fill = HEAD_FILL
        cell.alignment = Alignment(horizontal="center", wrap_text=True)
    ws.freeze_panes = "A2"


def autosize(ws, maxw=45):
    for col in ws.columns:
        w = max((len(str(c.value)) for c in col if c.value is not None), default=8)
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(w + 2, maxw)


def base_font(ws):
    for row in ws.iter_rows():
        for c in row:
            if c.font is None or c.font.name != ARIAL:
                c.font = Font(name=ARIAL, bold=c.font.bold if c.font else False,
                              color=c.font.color if c.font else None)


def main():
    berufe = read_csv("berufe.csv")
    snaps = read_csv("snapshots.csv")
    log = read_csv("jobs_log.csv")
    if not berufe or not snaps:
        print("FEHLER: keine Daten gefunden, zuerst collect_jobs.py laufen lassen.")
        return 1

    daten = sorted({r["datum"] for r in berufe})
    stand = daten[-1]
    stand_d = as_date(stand)
    regionen = sorted({r["region"] for r in berufe})
    reg_name = lambda r: REGION_NAMEN.get(r, r)

    # Vergleichsdaten: naechster vorhandener Stichtag ca. 7 bzw. 30 Tage zurueck
    def vergleich(tage):
        ziel = [d for d in daten if (stand_d - as_date(d)).days >= tage]
        return ziel[-1] if ziel else None
    d7, d30 = vergleich(7), vergleich(30)

    # Bestaende je (datum, region, beruf) und je (datum, beruf) gesamt
    brb = {}
    for r in berufe:
        brb[(r["datum"], r["region"], r["beruf"])] = int(r["anzahl"])
    bges = {}
    for r in berufe:
        k = (r["datum"], r["beruf"])
        bges[k] = bges.get(k, 0) + int(r["anzahl"])

    top_akt = sorted((b for (d, b) in bges if d == stand),
                     key=lambda b: -bges[(stand, b)])
    top20 = top_akt[:20]
    top40 = top_akt[:40]

    wb = Workbook()

    # ---------------- Zusammenfassung
    zs = wb.active
    zs.title = "Zusammenfassung"
    zs["A1"] = "Arbeitsmarkt-Auswertung Rems-Murr / Ostalb"
    zs["A1"].font = Font(name=ARIAL, bold=True, size=14)
    zs["A2"] = "Stand"
    zs["B2"] = stand_d
    zs["B2"].number_format = DATUM_FMT
    zs["A3"] = "Erhebungstage"
    zs["B3"] = len(daten)
    zs["A4"] = "Regionen"
    zs["B4"] = ", ".join(reg_name(r) for r in regionen)
    zs["A5"] = "Stellen je gesehen (Log)"
    zs["B5"] = len(log)
    zs["A7"] = ("Hinweis: Bei Regionen mit mehr als 6000 Treffern laedt die "
                "API nur 6000 Stellen im Detail. Die Berufs- und "
                "Arbeitgeberzahlen sind dort eine Stichprobe, die Spalte "
                "'Stellen gesamt' in der Zeitreihe ist exakt.")
    zs["A8"] = ("Arbeitslosenzahlen fuer das Blatt AL-Relation manuell aus "
                "statistik.arbeitsagentur.de eintragen (blaue Spalte).")
    for c in ("A2", "A3", "A4", "A5"):
        zs[c].font = Font(name=ARIAL, bold=True)

    # ---------------- Zeitreihe (snapshots: stellen_gesamt exakt)
    zt = wb.create_sheet("Zeitreihe")
    zt.append(["Datum"] + [reg_name(r) for r in regionen] + ["Gesamt"])
    snap_map = {(s["datum"], s["region"]): int(s["stellen_gesamt"]) for s in snaps}
    for i, d in enumerate(daten, start=2):
        zt.cell(row=i, column=1, value=as_date(d)).number_format = DATUM_FMT
        for j, r in enumerate(regionen, start=2):
            zt.cell(row=i, column=j, value=snap_map.get((d, r)))
        lc = get_column_letter(len(regionen) + 1)
        zt.cell(row=i, column=len(regionen) + 2,
                value=f"=SUM(B{i}:{lc}{i})")
    style_header(zt, len(regionen) + 2)
    for row in zt.iter_rows(min_row=2, min_col=2):
        for c in row:
            c.number_format = "#,##0"
    ch = LineChart()
    ch.title = "Offene Stellen je Region"
    ch.y_axis.title = "Stellen"
    ch.height, ch.width = 9, 18
    ref = Reference(zt, min_col=2, max_col=len(regionen) + 2,
                    min_row=1, max_row=len(daten) + 1)
    cats = Reference(zt, min_col=1, min_row=2, max_row=len(daten) + 1)
    ch.add_data(ref, titles_from_data=True)
    ch.set_categories(cats)
    zt.add_chart(ch, f"A{len(daten) + 4}")

    # ---------------- Berufe-Zeitreihe (Top 20, Summe ueber Regionen)
    bz = wb.create_sheet("Berufe-Zeitreihe")
    bz.append(["Datum"] + top20)
    for i, d in enumerate(daten, start=2):
        bz.cell(row=i, column=1, value=as_date(d)).number_format = DATUM_FMT
        for j, b in enumerate(top20, start=2):
            bz.cell(row=i, column=j, value=bges.get((d, b)))
    style_header(bz, len(top20) + 1)

    # ---------------- Aktuell
    ak = wb.create_sheet("Aktuell")
    kopf = (["Beruf"] + [reg_name(r) for r in regionen] +
            ["Gesamt", f"Vor 7 Tagen ({d7 or 'n/a'})",
             f"Vor 30 Tagen ({d30 or 'n/a'})", "Δ 7 Tage", "Δ 30 Tage"])
    ak.append(kopf)
    nr = len(regionen)
    col_ges = get_column_letter(nr + 2)
    col_v7 = get_column_letter(nr + 3)
    col_v30 = get_column_letter(nr + 4)
    for i, b in enumerate(top40, start=2):
        ak.cell(row=i, column=1, value=b)
        for j, r in enumerate(regionen, start=2):
            ak.cell(row=i, column=j, value=brb.get((stand, r, b)))
        ak.cell(row=i, column=nr + 2,
                value=f"=SUM(B{i}:{get_column_letter(nr + 1)}{i})")
        ak.cell(row=i, column=nr + 3, value=bges.get((d7, b)) if d7 else None)
        ak.cell(row=i, column=nr + 4, value=bges.get((d30, b)) if d30 else None)
        ak.cell(row=i, column=nr + 5,
                value=f'=IF({col_v7}{i}="","",{col_ges}{i}-{col_v7}{i})')
        ak.cell(row=i, column=nr + 6,
                value=f'=IF({col_v30}{i}="","",{col_ges}{i}-{col_v30}{i})')
    style_header(ak, nr + 6)
    bar = BarChart()
    bar.title = "Top 10 Berufe (gesamt, aktuell)"
    bar.height, bar.width = 9, 18
    bar.add_data(Reference(ak, min_col=nr + 2, min_row=1, max_row=11),
                 titles_from_data=True)
    bar.set_categories(Reference(ak, min_col=1, min_row=2, max_row=11))
    ak.add_chart(bar, f"A{len(top40) + 4}")

    # ---------------- Log (Rohdaten) + Standzeit-Formeln
    lg = wb.create_sheet("Log")
    lg.append(["Refnr", "Region", "Beruf", "Arbeitgeber",
               "Erstmals gesehen", "Zuletzt gesehen", "Standzeit (Tage)"])
    for i, r in enumerate(log, start=2):
        lg.cell(row=i, column=1, value=r["refnr"])
        lg.cell(row=i, column=2, value=reg_name(r["region"]))
        lg.cell(row=i, column=3, value=r["beruf"])
        lg.cell(row=i, column=4, value=r["arbeitgeber"])
        lg.cell(row=i, column=5, value=as_date(r["first_seen"])).number_format = DATUM_FMT
        lg.cell(row=i, column=6, value=as_date(r["last_seen"])).number_format = DATUM_FMT
        lg.cell(row=i, column=7, value=f"=F{i}-E{i}+1")
    style_header(lg, 7)
    nlog = len(log) + 1

    # ---------------- Standzeit je Beruf (Top 30 nach Log-Eintraegen)
    cnt = {}
    for r in log:
        cnt[r["beruf"]] = cnt.get(r["beruf"], 0) + 1
    top_log = sorted(cnt, key=lambda b: -cnt[b])[:30]
    st = wb.create_sheet("Standzeit")
    st.append(["Beruf", "Stellen im Log", "Aktuell offen",
               "Beendet", "Ø Standzeit beendeter Stellen (Tage)"])
    stand_ref = "Zusammenfassung!$B$2"
    for i, b in enumerate(top_log, start=2):
        st.cell(row=i, column=1, value=b)
        st.cell(row=i, column=2,
                value=f'=COUNTIF(Log!$C$2:$C${nlog},A{i})')
        st.cell(row=i, column=3,
                value=f'=COUNTIFS(Log!$C$2:$C${nlog},A{i},'
                      f'Log!$F$2:$F${nlog},{stand_ref})')
        st.cell(row=i, column=4,
                value=f'=COUNTIFS(Log!$C$2:$C${nlog},A{i},'
                      f'Log!$F$2:$F${nlog},"<"&{stand_ref})')
        st.cell(row=i, column=5,
                value=f'=IFERROR(ROUND(AVERAGEIFS(Log!$G$2:$G${nlog},'
                      f'Log!$C$2:$C${nlog},A{i},'
                      f'Log!$F$2:$F${nlog},"<"&{stand_ref}),1),"")')
    style_header(st, 5)

    # ---------------- Arbeitgeber (Top 25 nach offenen Stellen)
    off = {}
    for r in log:
        if r["last_seen"] == stand:
            off[r["arbeitgeber"]] = off.get(r["arbeitgeber"], 0) + 1
    top_ag = sorted(off, key=lambda a: -off[a])[:25]
    ag = wb.create_sheet("Arbeitgeber")
    ag.append(["Arbeitgeber", "Offene Stellen (aktuell)",
               "Stellen im Log gesamt"])
    for i, a in enumerate(top_ag, start=2):
        ag.cell(row=i, column=1, value=a)
        ag.cell(row=i, column=2,
                value=f'=COUNTIFS(Log!$D$2:$D${nlog},A{i},'
                      f'Log!$F$2:$F${nlog},{stand_ref})')
        ag.cell(row=i, column=3,
                value=f'=COUNTIF(Log!$D$2:$D${nlog},A{i})')
    style_header(ag, 3)

    # ---------------- AL-Relation (manuelle Eingabe)
    al = wb.create_sheet("AL-Relation")
    al.append(["Beruf", "Offene Stellen (aktuell)",
               "Arbeitslose (manuell, BA-Statistik)",
               "Arbeitslose je Stelle"])
    for i, b in enumerate(top20, start=2):
        al.cell(row=i, column=1, value=b)
        al.cell(row=i, column=2, value=f"=Aktuell!{col_ges}{i}")
        c_in = al.cell(row=i, column=3)
        c_in.font = INPUT_FONT
        al.cell(row=i, column=4,
                value=f'=IF(OR(C{i}="",B{i}=0),"",ROUND(C{i}/B{i},1))')
        al.cell(row=i, column=4).number_format = "0.0"
    style_header(al, 4)

    for ws in wb.worksheets:
        base_font(ws)
        autosize(ws)
    wb.save(OUT)
    print(f"Excel geschrieben: {OUT}")
    print(f"Stand {stand}, {len(daten)} Erhebungstage, "
          f"{len(log)} Stellen im Log.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
