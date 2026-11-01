"""Zuordnung der BA-Berufsbezeichnungen zu Branchen.

Die Jobsuche-API liefert kein Branchenfeld, nur die Berufsbezeichnung
(z.B. "Industriemechaniker/in"). Die Branche wird daher aus Schluesselwoertern
im Berufsnamen abgeleitet. Die Regeln werden von oben nach unten geprueft,
die erste passende gewinnt. Alles ohne Treffer landet in "Sonstige".
Neue Schluesselwoerter einfach in REGELN ergaenzen -- das Excel-Blatt
"Branchen" rechnet bei jedem Lauf komplett aus den Rohdaten neu, die
Zuordnung gilt damit auch rueckwirkend fuer alle Tage.
"""

import re

SONSTIGE = "Sonstige"

REGELN = [
    ("Gesundheit & Pflege", [
        "pflege", "kranken", "arzt", "ärztin", "medizin", "zahn", "therapeut",
        "physio", "ergo", "logopäd", "apothek", "pharma", "hebamme",
        "rettungs", "sanitäter", "heilpraktiker", "optiker", "orthopädie",
        "radiolog", "labor", "psycholog", "betreuungskraft", "alltagsbegleiter",
        "operationstechn", "anästhesie", "diätassist", "tierarzt", "tiermedizin",
        "podolog", "masseur", "krankenhaus", "hygieniker", "hörakustik", "kodier", "dental"]),
    ("Soziales & Bildung", [
        "erzieher", "sozial", "heilerziehung", "kinder", "lehrer", "lehrkraft",
        "pädagog", "dozent", "ausbilder", "schulbegleit", "kita", "jugend",
        "betreuer", "seelsorg", "hauswirtschaft", "familienpfleg", "tagesmutter"]),
    ("IT & Telekommunikation", [
        "informatik", "software", "programmier", "it-", "entwickler", "web",
        "netzwerk", "daten", "cloud", "devops", "systemadmin",
        "systemintegr", "cyber", "telekommunikation", "ux", "scrum", "sap-",
        "anwendungs", "datenbank", "digital", "erp", "business-analyst", "business analyst", "ki-", "data ", "data-", "supporter", "edv", "sps-", "admin"]),
    ("Logistik & Verkehr", [
        "lager", "logistik", "kraftfahrer", "fahrer", "gabelstapler", "stapler",
        "kommissionier", "fuhrpark", "speditions", "transport", "zusteller", "kurier",
        "post", "paket", "versand", "disponent", "fahrzeugführ", "lokführer",
        "busfahrer", "taxi", "flug", "schiff", "zugbegleit", "verkehr"]),
    ("Handel & Verkauf", [
        "verkäufer", "verkauf", "einzelhandel", "filial", "kassier", "handel",
        "fachverkäufer", "drogerie", "kaufmann/-frau - gross", "großhandel",
        "vertrieb", "kundenberater", "einkäufer", "einkauf", "merchandis",
        "außendienst", "key account", "tankstelle", "verkaufsberater",
        "buchhändler", "florist", "account-manager", "sales", "promoter", "kundendienst", "produktmanager"]),
    ("Gastronomie & Tourismus", [
        "koch", "köchin", "küche", "gastronomie", "gastgewerbe", "restaurant",
        "servicekraft", "servicemitarbeiter", "service-mitarbeiter", "hotel", "barkeeper", "barista", "sous-chef", "housekeeper", "hausdame", "kellner", "bäcker", "konditor", "fleischer",
        "metzger", "tourismus", "reisebüro", "systemgastronomie",
        "lebensmittel", "brauer", "winzer"]),
    ("Bau & Handwerk", [
        "bau", "maurer", "zimmer", "dachdeck", "maler", "lackierer", "tischler",
        "schreiner", "sanitär", "heizung", "klima", "anlagenmechaniker",
        "fliesen", "trockenbau", "gerüst", "estrich", "straßenbau",
        "tiefbau", "hochbau", "architekt", "vermessung", "glaser", "stuck",
        "installateur", "rollladen", "bodenleger", "raumausstatt", "steinmetz",
        "garten", "landschaft", "hausmeister", "gebäude", "schornstein",
        "kälte", "spengler", "klempner", "betonbauer", "gleisbauer", "rohrleitungsbau", "bagger", "straßenwärter", "statiker", "systemplaner", "kalkulator", "friseur", "kosmetik", "schneider", "goldschmied"]),
    ("Elektro & Energie", [
        "elektro", "elektron", "energie", "mechatronik", "photovoltaik",
        "automatisierung", "schaltanlagen", "nachrichtentechnik",
        "kabel", "solar", "elektriker", "industrieelektr", "netzmonteur", "mess-", "steuerungs", "regelungs"]),
    ("Büro, Verwaltung & Finanzen", [
        "büro", "buchhalt", "steuer", "kaufmann", "kauffrau", "kaufmänn",
        "verwaltung", "sachbearbeit", "sekretär", "assistenz", "assistent",
        "bank", "versicherung", "finanz", "controll", "personal", "recht",
        "betriebswirt", "recruiter", "hr ", "compliance", "business-development", "key-account", "supply-chain", "sourcing", "lean-", "facility", "industriekauf", "jurist", "anwalt", "notar", "bilanz", "lohn", "empfang", "büromanag",
        "projektleit", "projektmanag", "geschäftsführ", "unternehmensberat",
        "marketing", "social-media", "event-manager", "telefonist", "redakt", "journalis", "bürokraft", "sachbearbeiter",
        "rechnungswesen", "wirtschaftsprüf", "immobilien", "referent", "organisation", "kundenservice", "callcenter",
        "call-center", "dolmetsch", "übersetz"]),
    ("Industrie & Produktion", [
        "mechaniker", "mechatroniker", "zerspan", "dreher",
        "fräser", "cnc", "schweiß", "metall", "maschinen", "anlagenführer",
        "montierer", "monteur", "produktion", "fertigung", "werkzeug",
        "kunststoff", "kautschuk", "verfahrens", "chemie", "chemikant",
        "gießer", "schlosser", "techniker", "ingenieur", "konstrukteur",
        "qualitätssich", "qualitätsmanag", "fahrzeug", "kfz", "kraftfahrzeug", "karosserie", "lack",
        "oberflächen", "galvani", "papier", "glas", "verpackung", "textil", "holz",
        "feinwerk", "helfer/in - metall", "bediener", "instandhalt",
        "fachkraft - metall", "maschinenbau", "prüfer", "stanz",
        "druck", "werkstatt", "meister", "qualitätskontroll", "physiker", "engineer", "reklame", "löter", "arbeitsvorbereit", "schichtführ", "abfüller", "schleifer", "demontage", "mediengest", "betriebsschlosser", "werkstoff"]),
    ("Reinigung & Sicherheit", [
        "reinig", "sicherheit", "wachmann", "wach-", "security", "gebäudereinig",
        "hausmeister", "facility", "entsorgung", "abfall", "müll", "desinfekt", "wäscherei",
        "textilreinig", "objektschutz", "pförtner"]),
    ("Land- & Forstwirtschaft", [
        "landwirt", "forst", "agrar", "gärtner", "tierpfleg", "tierwirt",
        "pferde", "gartenbau", "obst", "weinbau", "fischerei", "schäfer",
        "landmaschinen"]),
    ("Helfer allgemein", ["helfer", "hilfskraft", "aushilfe"]),
]

_KOMPILIERT = None


def _regeln():
    global _KOMPILIERT
    if _KOMPILIERT is None:
        # kurze Woerter (<= 4 Zeichen) nur am Wortanfang suchen, sonst
        # trifft z.B. "erp" in "Zierpflanzenbau" oder "bau" in "Zierpflanzenbau"
        _KOMPILIERT = [(b, re.compile("|".join(
            (r"(?<![a-zäöüß])" if len(w) <= 4 else "") + re.escape(w.lower())
            for w in woerter))) for b, woerter in REGELN]
    return _KOMPILIERT


_cache: dict[str, str] = {}


def branche_von_beruf(beruf: str) -> str:
    if beruf in _cache:
        return _cache[beruf]
    s = re.sub(r"\s+", " ", (beruf or "").lower())
    erg = SONSTIGE
    for branche, muster in _regeln():
        if muster.search(s):
            erg = branche
            break
    _cache[beruf] = erg
    return erg
