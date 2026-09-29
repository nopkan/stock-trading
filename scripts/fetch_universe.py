"""Archive official SET lists; extract exactly 100 numbered constituents per PDF.

Snapshots are NOT a point-in-time membership table. Revision publication dates
and actual effective dates need reconciliation before historical eligibility use.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.set.or.th/en/market/information/securities-list/constituents-list-set50-set100"


def extract(path):
    pages = [p.extract_text() or "" for p in PdfReader(path).pages]
    start = next(i for i, text in enumerate(pages)
                 if re.search(r"(?<!&)SET100(?:/SET100FF)?INDEXCONSTITUENTS",
                              re.sub(r"\s+", "", text).upper()))
    numbered = {}
    for text in pages[start:]:
        for line in text.splitlines():
            # Older PDFs have two independent numbered columns on each line.
            matches = list(re.finditer(r"(?:^|\s)(\d{1,3})\s*\*?\s+\*?([A-Z0-9][A-Z0-9.&_-]*)\*?\s+", line))
            for j, match in enumerate(matches):
                number = int(match[1])
                if not 1 <= number <= 100 or number in numbered:
                    continue  # Later reserve-list rows repeat low numbers.
                stop = matches[j+1].start() if j+1 < len(matches) else len(line)
                numbered[number] = {"symbol": match[2], "yahoo_symbol": match[2] + ".BK",
                                    "company_and_sector": line[match.end():stop].strip()}
                if len(numbered) == 100:
                    rows = [numbered[n] for n in range(1, 101)]
                    assert len({r['symbol'] for r in rows}) == 100
                    return rows
    raise ValueError(f"Expected 100 numbered rows, extracted {len(numbered)}: {path.name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args()
    source = ROOT / "data/sources"
    universe = ROOT / "data/universe"
    source.mkdir(parents=True, exist_ok=True)
    universe.mkdir(parents=True, exist_ok=True)
    response = requests.get(URL, timeout=45)
    response.raise_for_status()
    (source / "constituents_page.html").write_text(response.text)
    links = list(dict.fromkeys(re.findall(r'https://media\.set\.or\.th/[^\s<>"\x27]+\.pdf', response.text)))
    links = [u for u in links if re.search(r"SET50.*(?:100).*H[12]_?[-_]?(?:20\d\d)", u)]
    if not links:
        raise RuntimeError("No constituent PDFs discovered; SET page structure may have changed")
    # Page order is newest first; keep source order and source metadata for review.
    if not args.archive:
        links = links[:1]
    manifest, snapshots = [], []
    for i, url in enumerate(links):
        path = source / url.rsplit("/", 1)[1]
        item = {"url": url, "file": str(path.relative_to(ROOT))}
        try:
            if not path.exists():
                r = requests.get(url, timeout=45)
                r.raise_for_status()
                path.write_bytes(r.content)
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
            rows = extract(path)
            for row in rows:
                row.update(source_url=url, source_file=path.name)
            snapshots.extend(rows)
            if i == 0:
                pd.DataFrame(rows).to_csv(universe / "set100_snapshot.csv", index=False)
            item.update(status="ok", constituents=len(rows))
        except Exception as exc:
            item.update(status="error", error=str(exc))
        print(path.name, item["status"], flush=True)
        manifest.append(item)
    pd.DataFrame(snapshots).to_csv(universe / "archived_snapshots.csv", index=False)
    (ROOT / "data/metadata/universe_sources.json").write_text(json.dumps({
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "listing_url": URL, "membership_type": "snapshots_not_effective_intervals",
        "sources": manifest}, indent=2))
    if manifest[0]["status"] != "ok":
        raise RuntimeError("Latest snapshot failed; no usable current universe")


if __name__ == "__main__":
    main()
