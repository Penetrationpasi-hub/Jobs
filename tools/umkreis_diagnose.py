"""Arbeitsorte in den vorhandenen Logs untersuchen (keine Rohdaten aendern)."""
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from umkreis import pruefe_ort


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    for filename in ("jobs_log.csv", "scrapjobs_log.csv"):
        with (ROOT / "data" / filename).open(encoding="utf-8", newline="") as f:
            counts = Counter(r["ort"] for r in csv.DictReader(f))
        print(filename, "Orte:", len(counts), "Stellen:", sum(counts.values()))
        totals = Counter()
        for name, n in counts.most_common():
            status, km = pruefe_ort(name)
            totals[status] += n
            if status == "unklar":
                print(n, name)
        print(totals)


if __name__ == "__main__":
    main()
