"""Zuordnung der BA-Berufsbezeichnungen zu den offiziellen Berufssegmenten.

Grundlage ist die Klassifikation der Berufe 2010 (KldB 2010) der Bundes-
agentur fuer Arbeit und deren Zusammenfassung in Berufssektoren und
Berufssegmente (Methodenbericht der BA-Statistik "Berufssektoren und
Berufssegmente auf Grundlage der KldB 2010"):

    KldB-Code (5-stellig) -> Berufshauptgruppe (2-Steller, 37 Stueck)
                          -> Berufssegment (14)  -> Berufssektor (5)

Die Segmente entstehen ausschliesslich aus den Berufshauptgruppen, es gibt
keine Ausnahmen auf 3-Steller-Ebene. Die Segmentnamen sind exakt dieselben
wie in der BA-Statistik (data_historie/ba_berufe.csv), damit Stellen und
Arbeitslose je Segment direkt nebeneinander stehen koennen.

Woher der KldB-Code eines Berufs kommt (Feld "quelle" der Einordnung):
  "Hand"      data/beruf_kldb_manuell.csv  (Korrekturen, haben Vorrang)
  "KldB"      data/beruf_kldb.csv          (automatisch per BERUFENET,
                                            tools/kldb_zuordnung.py)
  "Stichwort" Rueckfall ueber REGELN unten (Schluesselwoerter -> Haupt-
              gruppe), solange ein Beruf noch nicht nachgeschlagen ist oder
              BERUFENET ihn nicht kennt; auch fuer freie Titel (ScrapJobs)
  "offen"     nichts gefunden -> Segment "Keine Angabe" (BA-Begriff)

Alles wird bei jedem Lauf aus den Rohdaten neu gerechnet, Korrekturen
wirken damit rueckwirkend fuer alle Tage.
"""

import csv
import os
import re
from collections import namedtuple

SONSTIGE = "Keine Angabe"

# ---------------------------------------------------------------- Tabellen
SEKTOREN = {
    "S1": "Produktionsberufe",
    "S2": "Personenbezogene Dienstleistungsberufe",
    "S3": "Kaufmännische und unternehmensbezogene Dienstleistungsberufe",
    "S4": "IT- und naturwissenschaftliche Dienstleistungsberufe",
    "S5": "Sonstige wirtschaftliche Dienstleistungsberufe",
}

# Segmentcode -> Name, exakt wie in der BA-Statistik
SEGMENTE = {
    "S11": "Land-, Forst- und Gartenbauberufe",
    "S12": "Fertigungsberufe",
    "S13": "Fertigungstechnische Berufe",
    "S14": "Bau- und Ausbauberufe",
    "S21": "Lebensmittel- und Gastgewerbeberufe",
    "S22": "Medizinische u. nicht-medizinische Gesundheitsberufe",
    "S23": "Soziale und kulturelle Dienstleistungsberufe",
    "S31": "Handelsberufe",
    "S32": "Berufe in Unternehmensführung und -organisation",
    "S33": "Unternehmensbezogene Dienstleistungsberufe",
    "S41": "IT- und naturwissenschaftliche Dienstleistungsberufe",
    "S51": "Sicherheitsberufe",
    "S52": "Verkehrs- und Logistikberufe",
    "S53": "Reinigungsberufe",
}

# Kurze Anzeigenamen fuer Diagrammachsen (Tabellen zeigen den vollen Namen)
SEGMENT_KURZ = {
    "S11": "Land/Forst/Garten",
    "S12": "Fertigung",
    "S13": "Fertigungstechnik",
    "S14": "Bau & Ausbau",
    "S21": "Lebensmittel & Gastro",
    "S22": "Gesundheit",
    "S23": "Soziales & Kultur",
    "S31": "Handel",
    "S32": "Unternehmensführung",
    "S33": "Unternehmensbez. DL",
    "S41": "IT & Naturwiss.",
    "S51": "Sicherheit",
    "S52": "Verkehr & Logistik",
    "S53": "Reinigung",
    "": "Keine Angabe",
}

# Berufshauptgruppe (2-Steller) -> (Name, Segmentcode)
HAUPTGRUPPEN = {
    "01": ("Angehörige der regulären Streitkräfte", "S51"),
    "11": ("Land-, Tier- und Forstwirtschaftsberufe", "S11"),
    "12": ("Gartenbauberufe und Floristik", "S11"),
    "21": ("Rohstoffgewinnung, Glas- und Keramikherstellung und -verarbeitung", "S12"),
    "22": ("Kunststoffherstellung und -verarbeitung, Holzbe- und -verarbeitung", "S12"),
    "23": ("Papier- und Druckberufe, technische Mediengestaltung", "S12"),
    "24": ("Metallerzeugung und -bearbeitung, Metallbauberufe", "S12"),
    "25": ("Maschinen- und Fahrzeugtechnikberufe", "S13"),
    "26": ("Mechatronik-, Energie- und Elektroberufe", "S13"),
    "27": ("Technische Forschungs-, Entwicklungs-, Konstruktions- und Produktionssteuerungsberufe", "S13"),
    "28": ("Textil- und Lederberufe", "S12"),
    "29": ("Lebensmittelherstellung und -verarbeitung", "S21"),
    "31": ("Bauplanungs-, Architektur- und Vermessungsberufe", "S14"),
    "32": ("Hoch- und Tiefbauberufe", "S14"),
    "33": ("(Innen-)Ausbauberufe", "S14"),
    "34": ("Gebäude- und versorgungstechnische Berufe", "S14"),
    "41": ("Mathematik-, Biologie-, Chemie- und Physikberufe", "S41"),
    "42": ("Geologie-, Geografie- und Umweltschutzberufe", "S41"),
    "43": ("Informatik-, Informations- und Kommunikationstechnologieberufe", "S41"),
    "51": ("Verkehrs- und Logistikberufe (außer Fahrzeugführung)", "S52"),
    "52": ("Führer/innen von Fahrzeug- und Transportgeräten", "S52"),
    "53": ("Schutz-, Sicherheits- und Überwachungsberufe", "S51"),
    "54": ("Reinigungsberufe", "S53"),
    "61": ("Einkaufs-, Vertriebs- und Handelsberufe", "S31"),
    "62": ("Verkaufsberufe", "S31"),
    "63": ("Tourismus-, Hotel- und Gaststättenberufe", "S21"),
    "71": ("Berufe in Unternehmensführung und -organisation", "S32"),
    "72": ("Berufe in Finanzdienstleistungen, Rechnungswesen und Steuerberatung", "S33"),
    "73": ("Berufe in Recht und Verwaltung", "S33"),
    "81": ("Medizinische Gesundheitsberufe", "S22"),
    "82": ("Nichtmedizinische Gesundheits-, Körperpflege- und Wellnessberufe, Medizintechnik", "S22"),
    "83": ("Erziehung, soziale und hauswirtschaftliche Berufe, Theologie", "S23"),
    "84": ("Lehrende und ausbildende Berufe", "S23"),
    "91": ("Sprach-, literatur-, geistes-, gesellschafts- und wirtschaftswissenschaftliche Berufe", "S23"),
    "92": ("Werbung, Marketing, kaufmännische und redaktionelle Medienberufe", "S33"),
    "93": ("Produktdesign und kunsthandwerkliche Berufe, bildende Kunst, Musikinstrumentenbau", "S12"),
    "94": ("Darstellende und unterhaltende Berufe", "S23"),
}


def sektor_von_segment(seg: str) -> str:
    return seg[:2] if seg else ""


# --------------------------------------------------- Stichwort-Rueckfall
# (Hauptgruppe, [Schluesselwoerter]) -- von oben nach unten, erste passende
# Regel gewinnt; die REIHENFOLGE ist wichtig (Spezielles vor Allgemeinem,
# z.B. "Altenpflege" (82) vor "pflege" (81), "Kfz-Mechatroniker" (25) vor
# "mechatronik" (26), "Fachverkaeufer Baeckerei" (62) vor "baecker" (29)).
# Woerter mit hoechstens 4 Zeichen zaehlen nur am Wortanfang.
REGELN = [
    # --- Sonderfaelle, die sonst an allgemeineren Woertern haengen bleiben
    ("73", ["krankenkasse", "sozialversicherung", "rentenversicherung",
            "verwaltungswirt", "verwaltungsfach", "verwaltungsangest",
            "fachanwalt"]),
    ("72", ["(bank", "sparkasse", "wertpapier", "kredit"]),
    ("63", ["bankett", "büfett", "gästebetreu"]),
    ("53", ["sicherheitsgewerbe"]),
    ("43", ["cyber", "informationssicherheit", "it-sicherheit",
            "information-security", "information security", "(it)",
            "data engineer", "ki-", "product owner", "identity",
            "embedded", "anwendungsberat"]),
    ("26", ["glasfaser", "informations-, kommunikationstechn", "netzplan"]),
    ("62", ["einzelhandel", "fachverkäufer"]),
    ("31", ["bauzeichn", "bautechnische/r konstrukt", "landschaftsarchitekt",
            "ingenieur/in - landschaftsbau", "bauingenieur", "statiker",
            "bauabrechn", "stadt- und regionalplan", "montageleiter/in (bau"]),
    ("24", ["brennschneid", "konstruktionsmechan", "feinpolier"]),
    ("22", ["holzmechan"]),
    ("27", ["technische/r zeichner", "technische/r produktdesign",
            "lean-", "produktionstechnolog", "prozessmanag"]),
    ("81", ["facharzt", "psychotherap", "dentalhygien", "praxismanag"]),
    ("34", ["kältetechn", "kälteanlag", "klimatechn"]),
    ("33", ["rollladen"]),
    ("21", ["betonfertigteil"]),
    ("82", ["orthopädieschuh", "orthopädietechn"]),
    ("93", ["goldschmied", "silberschmied"]),
    ("94", ["veranstaltungstechn", "bühnen", "spielhall"]),
    ("54", ["fahrzeugpfleg", "fahrzeugaufbereit", "reinig", "dekont", "wäscherei", "desinfekt",
            "raumpfleg", "putz"]),
    # --- Bundeswehr
    ("01", ["soldat", "bundeswehr", "streitkräfte", "offizier"]),
    # --- Lehre, Erziehung, Soziales
    ("84", ["pflegepädagog", "fahrlehrer", "lehrer", "lehrkraft", "dozent",
            "ausbilder", "professor", "praxisanleit", "trainer", "nachhilfe"]),
    ("83", ["heilerziehung", "kinderpfleg", "familienpfleg", "sozialpädagog",
            "heilpädagog", "kindheitspädagog", "erzieher", "sozialarbeit",
            "sozialbetreu", "schulbegleit", "kinderbetreu", "tagesmutter",
            "tagesvater", "hauswirtschaft", "haushälter", "dorfhelfer",
            "haushaltsführung", "seelsorg", "diakon", "pfarrer", "kita",
            "kindertages", "kindergarten", "jugend", "integrationsfach", "inklusion",
            "jobcoach", "arbeitserzieh", "pädagog", "sprachförder"]),
    # --- Gesundheit
    ("82", ["altenpfleg", "betreuungskraft", "alltagsbegleit", "friseur",
            "kosmetik", "nageldesign", "visagist", "zahntechn", "augenoptik",
            "hörakustik", "medizintechn", "bestatt", "wellness",
            "diätassist", "ernährungsberat"]),
    ("11", ["tierpfleg", "tierwirt", "landwirt", "pferdewirt", "forstwirt",
            "forst", "agrar", "fischwirt", "schäfer", "winzer", "imker",
            "landwirtschaft"]),
    ("12", ["gärtner", "garten", "landschaftsgestalt", "landschaftsbau",
            "florist", "friedhof", "baumpfleg", "baumschul"]),
    ("81", ["pflege", "kranken", "arzt", "ärztin", "ärztlich",
            "medizinische/r fachangest", "zahnmedizin", "physiotherap",
            "ergotherap", "logopäd", "therapeut", "hebamme", "entbindung",
            "rettungs", "notfallsanit", "sanitäter", "operationstechn",
            "anästhesietechn", "radiolog", "medizinisch-techn",
            "medizinische/r technolog", "pharmazeut", "apothek", "psycholog",
            "psychotherap", "heilpraktik", "masseur", "podolog", "osteopath",
            "wundmanag", "stationsleit", "medizin", "tiermedizin", "kodier",
            "intensiv", "dialyse", "orthoptist"]),
    # --- Sicherheit (enge Woerter: Sicherheitstechnik bleibt Technik)
    ("53", ["sicherheitsmitarbeit", "sicherheitskraft", "sicherheitsdienst",
            "sicherheitsfach", "sicherheitsmanag", "schutz und sicherheit",
            "schutz- und sicherheit", "arbeitssicherheit", "gesundheitsschutz",
            "arbeitsschutz", "wachmann", "wach-", "bewach", "security",
            "objektschutz", "werkschutz", "pförtner", "detektiv", "brandschutz",
            "feuerwehr", "polizei", "justizvollzug", "ordnungsdienst",
            "bäderbetrieb", "schwimmmeister", "rettungsschwimm"]),
    # --- Fahrzeugfuehrung vor Logistik/Maschinen
    ("52", ["gabelstapler", "stapler", "kraftfahrer", "fahrer", "kranführer",
            "baumaschinenführer", "baugeräteführer", "baggerführer",
            "lokführer", "triebfahrzeug", "taxi", "chauffeur", "pilot",
            "schiffsführ", "binnenschiff", "fahrzeugführ", "personenbeförder"]),
    ("51", ["lager", "logistik", "kommissionier", "spedition", "disponent/in - güter",
            "disponent/in - lager", "eisenbahner", "fuhrpark", "versand", "zusteller", "zustell", "kurier",
            "post", "paket", "brief- und fracht", "frachtverkehr", "umzug",
            "zugbegleit", "fahrdienstleit", "verkehrsservice", "supply-chain",
            "materialwirtschaft", "warenannahme", "warenannehm",
            "transportarbeit", "luftverkehr", "flughafen", "hafen"]),
    # --- Handel
    ("61", ["einkäufer", "einkauf", "vertrieb", "außendienst", "key-account",
            "key account", "account-manager", "sales", "verkaufsleit",
            "handelsvertret", "großhandel", "außenhandel", "immobilien",
            "objektverwalt", "produktmanag", "category", "automobilkauf",
            "kundenberater", "kundendienstberater", "e-commerce",
            "marktforsch", "serviceberat", "innendienst", "sourcing",
            "pharmareferent"]),
    ("62", ["verkäufer", "verkauf", "kassierer", "kasse", "einzelhandel",
            "filialleit", "filial", "verkaufsstellenleit", "fachverkäufer",
            "drogist", "tankstell", "promoter", "fachberater/in - bau- und heimwerk",
            "küchenplan", "einrichtungsfachberat", "warenverräum",
            "regalauffüll", "buchhändl"]),
    # --- Lebensmittel und Gastgewerbe
    ("29", ["koch", "köchin", "beikoch", "küche", "küchenchef", "sous-chef",
            "bäcker", "konditor", "fleischer", "metzger", "lebensmittel",
            "nahrungsmittel", "brauer", "mälzer", "getränke", "molkerei",
            "milchtechnolog", "süßwaren", "abfüller"]),
    ("63", ["gastronomie", "gastgewerbe", "restaurant", "hotel", "kellner",
            "barkeeper", "barista", "housekeep", "hausdame", "zimmermädchen",
            "rezeption", "systemgastronom", "tourismus", "reiseverkehr",
            "reisebüro", "reiseleit", "veranstaltungskauf", "event", "catering"]),
    # --- Fahrzeugtechnik (vor Mechatronik/Elektro)
    ("25", ["maschinenbau", "maschinentechn", "land- und baumaschinen",
            "instandhaltungstechn", "wartungs- und servicetechn",
            "werkstattleit", "demontage"]),
    ("25", ["kraftfahrzeug", "kfz", "fahrzeugtechn", "fahrzeugbau",
            "karosserie", "automobilmechan", "zweirad", "fahrrad",
            "landmaschin", "baumaschinenmechan", "nutzfahrzeug",
            "luft- und raumfahrt", "fluggerät", "reifen",
            "maschinen- und anlagenführer/in (ohne", "kundendienstmont"]),
    # --- Elektro, Mechatronik, Energie
    ("26", ["mechatronik", "elektro", "elektronik", "elektrik", "energie",
            "automatisierung", "sps", "photovoltaik", "solar", "kabel",
            "netzmonteur", "freileitung", "inbetriebnahme", "mess- und regel",
            "steuerungstechn", "regelungstechn", "alarmanlag",
            "sicherheits-/alarm", "kommunikationselektron"]),
    # --- IT
    ("43", ["informatik", "software", "programmier", "it-", "- it", "it ",
            "softwareentwickl", "anwendungsentwickl", "webentwickl", "web-",
            "frontend", "backend", "fullstack", "netzwerk", "systemadmin",
            "systembetreu", "systemintegr", "cloud", "devops", "data scien",
            "data-", "datenbank", "datenanalyse", "erp", "sap", "edv",
            "first-level", "second-level", "supporter", "ux", "scrum",
            "telekommunikation", "kundenbetreuer/in - it"]),
    # --- Bau und Gebaeude
    ("34", ["anlagenmechaniker", "sanitär", "heizung", "lüftung", "klempner",
            "spengler", "installateur", "hausmeister", "hauswart", "haustechn",
            "gebäudetechn", "gebäudeausrüst", "versorgungstechn", "facility", "objektbetreu",
            "schornstein", "ofenbau", "ver- und entsorgung", "entsorgung",
            "abwasser", "wasserversorg", "kreislauf- und abfall", "abfall",
            "müll", "recycling", "umwelttechnolog", "rohrleitungsbau"]),
    ("33", ["maler", "lackier", "trockenbau", "fliesen", "stuck", "bodenleg",
            "boden", "estrich", "parkett", "glaser", "raumausstatt", "isolier",
            "fassaden", "ausbau", "fenster", "farb- und lack", "messebau"]),
    ("32", ["maurer", "beton", "zimmerer", "zimmerin", "dachdeck",
            "straßenbau", "straßenwärter", "tiefbau", "hochbau", "gleisbau",
            "brunnenbau", "kanalbau", "polier", "gerüst", "pflaster",
            "bauwerksabdicht", "bauhelfer", "baufacharbeit", "bauarbeit",
            "abbruch"]),
    ("31", ["architekt", "bauzeichn", "bauleit", "bauingenieur",
            "ingenieur/in - bau", "hochbauingenieur", "tiefbauingenieur",
            "vermess", "geomatik", "stadtplan", "bauplan",
            "techniker/in - bautechnik", "assistent/in - bautechnik",
            "bauüberwach", "baukontroll", "kalkulator", "systemplaner"]),
    # --- Metall, Kunststoff/Holz, Papier/Druck, Glas, Textil
    ("24", ["zerspan", "cnc", "dreher", "fräser", "schleifer", "drehtechn",
            "frästechn", "metallbear", "metallbau", "metall", "schweiß",
            "konstruktionsmechan", "werkzeugmechan", "werkzeugmach",
            "werkzeugbau", "feinwerk", "feinmechan", "feinpolier", "gieß",
            "galvan", "oberflächenbeschicht", "beschichtungstechn", "löter",
            "stanz", "umformtechn", "blechbearb", "schmied", "uhrmacher",
            "nc-anwendung", "teilezuricht"]),
    ("22", ["kunststoff", "kautschuk", "holz", "tischler", "schreiner",
            "möbel", "drechsler", "parkettleg"]),
    ("23", ["papier", "verpackung", "druck", "mediengestalt",
            "medientechnolog", "buchbind", "fotograf", "reklame", "schilder",
            "werbetechn"]),
    ("21", ["glas", "keramik", "naturstein", "steinmetz", "bergbau",
            "bergmann", "baustoff", "aufbereitungsmechan"]),
    ("28", ["textil", "schneider", "näher", "bekleidung", "polster", "leder",
            "schuh", "modist", "strick", "konfektion"]),
    ("93", ["designer", "kunsthandwerk", "musikinstrument", "keramiker",
            "töpfer", "graveur", "vergolder", "restaurator", "bildhauer"]),
    ("94", ["musiker", "schauspiel", "sänger", "tänzer", "moderat",
            "animateur", "artist", "tontechn", "lichttechn", "kamera"]),
    # --- Naturwissenschaft, Umwelt
    ("41", ["chemie", "chemiker", "chemikant", "laborant", "labor", "biolog", "physik",
            "mathemat", "pharmatechn", "pharmakant", "biotechn"]),
    ("42", ["umweltschutz", "umweltingen", "geolog", "geograf", "geograph",
            "umweltberat", "meteorolog", "nachhaltigkeit"]),
    # --- Technik allgemein
    ("27", ["konstrukt", "technische/r zeichner", "technische/r produktdesign",
            "arbeitsvorbereit", "produktionsplan", "fertigungsplan",
            "prozessplan", "produktionssteuer", "qualitäts", "forschung",
            "entwicklungsingenieur", "produktentwickl", "versuchs",
            "prüftechn", "prüffeld", "schichtführ", "schichtleit",
            "produktionsleit", "leiter/in - produktion", "fertigungsleit",
            "industriemeister", "wirtschaftsingenieur", "ingenieur",
            "techniker", "engineer"]),
    ("25", ["industriemechan", "betriebsschlosser", "maschinenbau",
            "maschinen- und anlagenführ", "anlagenführ", "maschinenführ",
            "maschineneinricht", "einrichter", "montier", "montagemechan",
            "anlagenmonteur", "montagetechn", "monteur", "instandhalt",
            "wartungs", "servicetechn", "mechaniker", "schlosser",
            "maschinen"]),
    # --- Finanzen, Unternehmen, Recht/Verwaltung, Medien
    ("72", ["buchhalt", "bilanz", "lohn- und gehalt", "lohnbuch", "controll",
            "steuerfach", "steuerberat", "steuer", "finanz", "bank",
            "versicherung", "wirtschaftsprüf", "rechnungswesen", "kreditor",
            "debitor", "anlageberat"]),
    ("92", ["marketing", "werbekauf", "werbetext", "werbe-", "werbung", "crm-", "social-media", "social media",
            "online-market", "redakt", "journalis", "öffentlichkeitsarbeit",
            "kommunikationsmanag", "content", "verlag", "medienkauf",
            "grafikdesign", "kampagne"]),
    ("71", ["bürokauf", "büromanag", "bürokommunik", "büroassist", "büro",
            "sekretär", "empfang", "telefonist", "callcenter", "call-center",
            "kundenservice", "industriekauf", "kaufmännische fachkraft",
            "personal", "recruit", "human resources", "projektleit",
            "projektmanag", "projektkoordin", "projektassist",
            "geschäftsführ", "unternehmensberat", "betriebswirt",
            "management", "business", "office", "bereichsleit",
            "niederlassungsleit", "bezirksleit", "assistent", "assistenz",
            "kaufmann", "kauffrau", "kaufmännisch"]),
    ("73", ["verwaltungsfach", "verwaltungswirt", "verwaltung", "beamt",
            "jurist", "rechtsanwalt", "rechtsanwält", "notar", "rechtspfleg",
            "justiz", "sachbearbeit", "datenschutz", "compliance",
            "e-government", "bibliothek", "archiv", "dokumentar"]),
    ("91", ["dolmetsch", "übersetz", "volkswirt", "sozialwissenschaft",
            "soziolog", "politolog", "historik", "wirtschaftswissenschaft",
            "linguist", "kommunikationswissenschaft"]),
]

Einordnung = namedtuple(
    "Einordnung",
    "sektor segment segment_name hauptgruppe hauptgruppe_name kldb quelle")

_KOMPILIERT = None


def _regeln():
    global _KOMPILIERT
    if _KOMPILIERT is None:
        # kurze Woerter (<= 4 Zeichen) nur am Wortanfang suchen, sonst
        # trifft z.B. "erp" in "Zierpflanzenbau"
        _KOMPILIERT = [(hg, re.compile("|".join(
            (r"(?<![a-zäöüß])" if len(w) <= 4 else "") + re.escape(w.lower())
            for w in woerter))) for hg, woerter in REGELN]
    return _KOMPILIERT


def hauptgruppe_per_stichwort(text: str) -> str:
    """Hauptgruppe (2-Steller) aus Schluesselwoertern, "" wenn keine passt."""
    s = re.sub(r"\s+", " ", (text or "").lower())
    for hg, muster in _regeln():
        if muster.search(s):
            return hg
    return ""


# ---------------------------------------------------- KldB-Nachschlagetabellen
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
KLDB_DATEI = os.path.join(DATA_DIR, "beruf_kldb.csv")
KLDB_MANUELL = os.path.join(DATA_DIR, "beruf_kldb_manuell.csv")
KLDB_FELDER = ["beruf", "kldb", "berufenet_id", "berufenet_name", "quelle",
               "abgerufen"]

_kldb = None        # beruf -> (kldb5, quelle)


def kldb_ziffern(code: str) -> str:
    """'B 25102' / '25102' / '251' -> nur Ziffern."""
    return re.sub(r"\D", "", code or "")


def lade_kldb(neu=False):
    """Beide Tabellen laden; Handkorrekturen ueberschreiben den Cache."""
    global _kldb, _cache
    if _kldb is not None and not neu:
        return _kldb
    _kldb, _cache = {}, {}
    for pfad, quelle in ((KLDB_DATEI, "KldB"), (KLDB_MANUELL, "Hand")):
        if not os.path.exists(pfad):
            continue
        with open(pfad, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                code = kldb_ziffern(r.get("kldb"))
                if r.get("beruf") and len(code) >= 2 and code[:2] in HAUPTGRUPPEN:
                    _kldb[r["beruf"].strip()] = (code, quelle)
    return _kldb


def _aus_hg(hg, kldb, quelle):
    if hg not in HAUPTGRUPPEN:
        return Einordnung("", "", SONSTIGE, "", SONSTIGE, "", "offen")
    name, seg = HAUPTGRUPPEN[hg]
    return Einordnung(sektor_von_segment(seg), seg, SEGMENTE[seg], hg, name,
                      kldb, quelle)


_cache: dict = {}


def einordnung(beruf: str) -> Einordnung:
    """Sektor/Segment/Hauptgruppe eines BA-Berufs (oder freien Titels)."""
    beruf = (beruf or "").strip()
    if beruf in _cache:
        return _cache[beruf]
    treffer = lade_kldb().get(beruf)
    if treffer:
        erg = _aus_hg(treffer[0][:2], treffer[0], treffer[1])
    else:
        hg = hauptgruppe_per_stichwort(beruf)
        erg = _aus_hg(hg, "", "Stichwort") if hg else _aus_hg("", "", "offen")
    _cache[beruf] = erg
    return erg


def branche_von_beruf(beruf: str) -> str:
    """Segmentname (bzw. "Keine Angabe") -- frueherer Name der Funktion."""
    return einordnung(beruf).segment_name
