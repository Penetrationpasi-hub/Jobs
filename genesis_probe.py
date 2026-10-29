"""Read-only catalogue probe. Never log authentication parameters or responses."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://genesis.destatis.de/genesisWS/rest/2020"


def main():
    token = os.environ.get("GENESIS_TOKEN", "").strip()
    if not token:
        raise SystemExit("GENESIS_TOKEN is not available to this workflow.")
    reports = []
    queries = [
        ("catalogue/tables", {"selection": "13111*", "area": "all"}),
        ("catalogue/tables", {"selection": "13312*", "area": "all"}),
        ("find/find", {"term": "Berufe", "category": "tables"}),
    ]
    for endpoint, params in queries:
        params.update(language="de", pagelength="1000")
        request = urllib.request.Request(
            BASE + "/" + endpoint,
            data=urllib.parse.urlencode(params).encode(),
            headers={"username": token,
                     "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            reports.append({"query": params, "http_status": exc.code})
            continue
        except Exception:
            reports.append({"query": params, "error": "Network or decoding failure"})
            continue
        # Whitelist public catalogue fields; do not persist Parameter/Username.
        status = result.get("Status")
        entries = result.get("List") or result.get("Tables") or []
        report = {
            "query": params,
            "status_code": status.get("Code") if isinstance(status, dict) else None,
            "entries": [
                {key: item.get(key) for key in ("Code", "Content", "Time")}
                for item in entries
            ],
        }
        reports.append(report)
    text = json.dumps(reports, ensure_ascii=False, indent=2)
    # Defensive redaction even for unexpected upstream catalogue contents.
    text = text.replace(token, "[REDACTED]")
    print(text)
    with open("genesis_catalogue_report.json", "w", encoding="utf-8") as stream:
        stream.write(text)
    if not any(report.get("entries") for report in reports):
        raise SystemExit("No usable catalogue entries; workbook untouched.")


if __name__ == "__main__":
    main()
