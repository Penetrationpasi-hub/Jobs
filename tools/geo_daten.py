"""GeoNames-Postleitzahlorte fuer den reproduzierbaren Umkreisfilter laden."""
import csv
import io
import json
from pathlib import Path
import zipfile

import requests

ROOT = Path(__file__).resolve().parents[1]
URL = "https://download.geonames.org/export/zip/DE.zip"


def main():
    response = requests.get(URL, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        text = archive.read("DE.txt").decode("utf-8")
    rows = []
    for r in csv.reader(io.StringIO(text), delimiter="\t"):
        rows.append([r[1], r[2], float(r[9]), float(r[10]), r[3]])
    target = ROOT / "data" / "geo_orte.json"
    target.write_text(json.dumps({
        "quelle": URL, "lizenz": "CC BY 4.0, GeoNames (geonames.org)",
        "spalten": ["plz", "ort", "lat", "lon", "bundesland"], "orte": rows,
    }, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(rows)} Postleitzahlorte -> {target}")


if __name__ == "__main__":
    main()
