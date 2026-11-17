"""Ortsangabe -> Landkreis.

BA-Stellen haben einen Ortsnamen ("Waiblingen, Rems"), die Karriereseiten
aus ScrapJobs freien Text ("71332 Waiblingen DE-BW", "Winnenden, DE, 71364").
Beide werden hier auf denselben Kreis abgebildet. Das ergibt eine
ueberschneidungsfreie Regionsspalte (die BA-Suchgebiete sind Umkreise und
ueberlappen sich) und macht BA- und Karriereseiten-Stellen vergleichbar.

Erkannt wird ueber Gemeindenamen (inkl. bekannter Ortsteile). Bei mehreren
Orten im Text gewinnt der erste. Nicht erkannte Orte -> ANDERE,
leere Angaben -> OHNE_ORT. Neue Gemeinden einfach in KREISE ergaenzen.
"""

import re

ANDERE = "andere Region"
OHNE_ORT = "ohne Ortsangabe"

KREISE = {
    "Rems-Murr-Kreis": [
        "Rems-Murr-Kreis", "Waiblingen", "Backnang", "Fellbach", "Schorndorf",
        "Winnenden", "Weinstadt", "Kernen im Remstal", "Rommelshausen",
        "Remshalden", "Grunbach", "Urbach", "Plüderhausen", "Rudersberg",
        "Welzheim", "Alfdorf", "Murrhardt", "Sulzbach an der Murr",
        "Schwaikheim", "Leutenbach", "Korb", "Allmersbach im Tal",
        "Allmersbach", "Oppenweiler", "Weissach im Tal", "Burgstetten",
        "Kirchberg an der Murr", "Aspach", "Auenwald", "Berglen",
        "Großerlach", "Kaisersbach", "Althütte", "Spiegelberg", "Winterbach",
        "Hertmannsweiler", "Birkachhof", "Birkhof bei Alfdorf",
    ],
    "Ostalbkreis": [
        "Aalen", "Schwäbisch Gmünd", "Ellwangen", "Oberkochen", "Bopfingen",
        "Lorch", "Abtsgmünd", "Westhausen", "Neresheim", "Heubach",
        "Mögglingen", "Mutlangen", "Essingen", "Rosenberg", "Wört",
        "Fichtenau", "Bartholomä", "Lauchheim", "Waldstetten",
        "Böbingen an der Rems", "Neuler", "Spraitbach", "Eschach",
        "Riesbürg", "Schechingen", "Iggingen", "Rainau", "Ruppertshofen",
        "Unterschneidheim", "Adelmannsfelden", "Tannhausen", "Stödtlen",
        "Durlangen", "Heuchlingen", "Leinzell", "Täferrot", "Göggingen",
        "Hüttlingen", "Jagstzell", "Kirchheim am Ries", "Ellenberg",
        "Obergröningen", "Gschwend",
    ],
    "Stuttgart": ["Stuttgart"],
    "Landkreis Esslingen": [
        "Esslingen", "Kirchheim unter Teck", "Nürtingen",
        "Leinfelden-Echterdingen", "Filderstadt", "Ostfildern", "Plochingen",
        "Neuhausen auf den Fildern", "Denkendorf", "Wendlingen", "Wernau",
        "Altbach", "Deizisau", "Köngen", "Aichwald", "Wolfschlugen",
        "Reichenbach an der Fils", "Frickenhausen", "Dettingen unter Teck",
        "Neckartenzlingen", "Unterensingen", "Aichtal", "Neckartailfingen",
        "Baltmannsweiler", "Hochdorf bei Plochingen", "Oberboihingen",
        "Großbettlingen", "Lichtenwald", "Holzmaden", "Notzingen",
        "Altdorf bei Nürtingen", "Weilheim an der Teck", "Schlaitdorf",
        "Altenriet", "Bissingen an der Teck", "Ohmden",
    ],
    "Landkreis Ludwigsburg": [
        "Ludwigsburg", "Bietigheim-Bissingen", "Kornwestheim", "Ditzingen",
        "Freiberg am Neckar", "Korntal-Münchingen", "Remseck",
        "Marbach am Neckar", "Asperg", "Markgröningen", "Affalterbach",
        "Besigheim", "Gerlingen", "Vaihingen an der Enz", "Murr",
        "Möglingen", "Pleidelsheim", "Tamm", "Sachsenheim", "Erdmannhausen",
        "Kirchheim am Neckar", "Hemmingen", "Steinheim an der Murr",
        "Schwieberdingen", "Oberstenfeld", "Großbottwar", "Sersheim",
        "Benningen am Neckar", "Eberdingen", "Bönnigheim", "Ingersheim",
        "Gemmrigheim", "Löchgau", "Mundelsheim", "Erligheim", "Walheim",
        "Freudental", "Oberriexingen", "Hessigheim",
    ],
    "Landkreis Böblingen": [
        "Sindelfingen", "Böblingen", "Leonberg", "Renningen", "Weissach",
        "Magstadt", "Rutesheim", "Steinenbronn", "Schönaich", "Waldenbuch",
        "Herrenberg", "Weil im Schönbuch",
    ],
    "Landkreis Göppingen": [
        "Göppingen", "Ebersbach an der Fils", "Ebersbach", "Donzdorf",
        "Böhmenkirch", "Uhingen", "Rechberghausen", "Wangen Kreis Göppingen",
        "Albershausen", "Lauterstein", "Zell unter Aichelberg",
        "Wäschenbeuren", "Hattenhofen", "Börtlingen", "Süßen", "Aichelberg",
        "Salach", "Geislingen an der Steige", "Ottenbach", "Birenbach",
        "Schlierbach", "Adelberg", "Eislingen",
    ],
    "Heilbronn (Stadt und Land)": [
        "Heilbronn", "Ilsfeld", "Obersulm", "Abstatt", "Talheim Neckar",
        "Löwenstein", "Untergruppenbach", "Neckarwestheim", "Ellhofen",
        "Lauffen am Neckar", "Beilstein", "Flein", "Weinsberg",
        "Lehrensteinsfeld", "Brackenheim", "Cleebronn", "Wüstenrot",
    ],
    "Landkreis Schwäbisch Hall": [
        "Schwäbisch Hall", "Obersontheim", "Gaildorf", "Stimpfach",
        "Rosengarten", "Bühlertann", "Oberrot", "Sulzbach-Laufen",
        "Fichtenberg", "Mainhardt", "Michelfeld", "Frankenhardt",
        "Bühlerzell", "Crailsheim",
    ],
    "Landkreis Heidenheim": [
        "Heidenheim", "Giengen an der Brenz", "Herbrechtingen", "Gerstetten",
        "Steinheim am Albuch", "Königsbronn", "Nattheim", "Dischingen",
        "Hermaringen",
    ],
    "Hohenlohekreis": ["Pfedelbach", "Bretzfeld"],
    "Bayern (Donau-Ries, Ansbach, Dillingen)": [
        "Nördlingen", "Wallerstein", "Ederheim", "Forheim", "Fremdingen",
        "Reimlingen", "Marktoffingen", "Maihingen", "Donauwörth",
        "Dinkelsbühl", "Wilburgstetten", "Mönchsroth", "Syrgenstein",
        "Bachhagel", "Zöschingen", "Ziertheim",
    ],
}


def _norm(s):
    s = (s or "").lower().replace("ß", "ss")
    return " " + re.sub(r"[^a-zäöü0-9]+", " ", s).strip() + " "


_MUSTER = None
_ZUORDNUNG = {}
_cache = {}


def _muster():
    global _MUSTER
    if _MUSTER is None:
        for kreis, orte in KREISE.items():
            for o in orte:
                _ZUORDNUNG[_norm(o).strip()] = kreis
        # laengste zuerst: bei gleicher Startposition gewinnt der laengere
        # Name ("weissach im tal" vor "weissach", "murr" nur als ganzes Wort)
        namen = sorted(_ZUORDNUNG, key=len, reverse=True)
        _MUSTER = re.compile(r"(?<= )(" + "|".join(map(re.escape, namen)) + r")(?= )")
    return _MUSTER


def kreis_von(ort):
    """Kreis zu einer Ortsangabe (BA-Ortsname oder freier Text)."""
    if ort in _cache:
        return _cache[ort]
    t = _norm(ort)
    if not t.strip():
        erg = OHNE_ORT
    else:
        m = _muster().search(t)
        erg = _ZUORDNUNG[m.group(1)] if m else ANDERE
    _cache[ort] = erg
    return erg
