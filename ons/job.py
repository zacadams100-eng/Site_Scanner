"""
The scheduled ONS spreadsheet ingest.

    python3 -m ons.job --check                 # resolve URLs, parse nothing
    python3 -m ons.job                         # refresh everything
    python3 -m ons.job --only private_rents    # one dataset
    python3 -m ons.job --from-file rents.xlsx --only private_rents

Downloads each release named in `ons/datasets.py`, parses it, and writes
`data/ons/<dataset>.json`. `ons_store.py` reads those files at runtime, which
is what turns these factors from generated into real — with no database, no
credentials and no network on the request path, so it works in the serverless
deployment as well as locally.

## Why this is a job and not an API client

ONS publishes private rents, earnings, affordability and the census as
spreadsheets on a release page. There is no per-area endpoint to call.
`docs/OPEN-DATA.md` recorded this as the reason those factors stayed generated
while the rest of `open_data.py` went real; this is the fix it named.

## Failure is per dataset, and never destructive

One release moving its URL must not take the other four with it, so each is
downloaded, parsed and written independently, and a failure leaves the
previous file exactly where it was. A stale figure carrying its date is much
better than a wrong one and far better than an empty catalogue — and
`ons_store` reports the date, so nothing silently presents 2019 as current.

The job exits non-zero if anything failed, so a scheduled run that half-works
is visible rather than quietly degrading.
"""

import argparse
import datetime as dt
import io
import json
import pathlib
import sys
import zipfile
from typing import List, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ons import parse                                   # noqa: E402
from ons.datasets import DATASET_BY_ID, DATASETS, Dataset  # noqa: E402

STORE = ROOT / "data" / "ons"
TIMEOUT = 120
# Government sites reject the default python-requests agent often enough that
# it is worth being explicit about who is asking.
HEADERS = {"User-Agent": "SiteScanner/1.0 (+https://github.com/zacadams100-eng/Site_Scanner)"}


class FetchError(RuntimeError):
    pass


def fetch(url: str) -> bytes:
    import requests

    try:
        r = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
    except Exception as exc:                            # noqa: BLE001
        raise FetchError(f"{type(exc).__name__}: {exc}") from exc
    if not r.ok:
        raise FetchError(f"HTTP {r.status_code}")
    if b"<html" in r.content[:400].lower():
        # An ONS "page not found" is served as HTML with a 200 more often than
        # it should be. Parsing it would fail confusingly several steps later.
        raise FetchError("the server returned HTML, not a spreadsheet — the "
                         "release URL has almost certainly moved")
    return r.content


def workbook_bytes(payload: bytes, dataset: Dataset) -> bytes:
    """The spreadsheet, unwrapped from a zip if the release ships one."""
    if payload[:2] != b"PK":
        return payload
    # Both .xlsx and .zip start PK; a real .xlsx contains [Content_Types].xml.
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        names = z.namelist()
        if "[Content_Types].xml" in names:
            return payload
        sheets = [n for n in names if n.lower().endswith((".xlsx", ".xls"))]
        if not sheets:
            raise FetchError(f"the archive holds no spreadsheet: {names[:5]}")
        # ASHE ships several workbooks per zip; prefer one whose name matches
        # what the spec is after, and fall back to the first.
        wanted = dataset.columns[0].header_contains.lower()
        pick = next((n for n in sheets if wanted in n.lower()), sheets[0])
        return z.read(pick)


def refresh(dataset: Dataset, *, source: Optional[pathlib.Path] = None,
            store: pathlib.Path = STORE) -> dict:
    """Fetch, parse and write one dataset. Returns its manifest entry."""
    payload = source.read_bytes() if source else fetch(dataset.url)
    payload = workbook_bytes(payload, dataset)

    tmp = store / f".{dataset.id}.xlsx"
    store.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(payload)
    try:
        observations = parse.parse_workbook(tmp, dataset)
    finally:
        tmp.unlink(missing_ok=True)

    values = parse.to_store(observations)
    periods = sorted({p for byarea in values.values()
                      for periods in byarea.values() for p in periods})
    body = {
        "dataset": dataset.id,
        "title": dataset.title,
        "publisher": dataset.publisher,
        "licence": dataset.licence,
        "source_url": dataset.url,
        "page": dataset.page,
        "cadence": dataset.cadence,
        "retrieved": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "latest_period": periods[-1] if periods else None,
        "observations": len(observations),
        "values": values,
    }
    # Written whole, then moved: a scheduled job killed mid-write must not
    # leave a truncated file that parses as valid JSON up to the cut.
    out = store / f"{dataset.id}.json"
    scratch = store / f".{dataset.id}.json.tmp"
    scratch.write_text(json.dumps(body, separators=(",", ":"), sort_keys=True))
    scratch.replace(out)
    return body


def check(dataset: Dataset) -> str:
    """Resolve the URL and report, without parsing. For finding dead links
    before a real run, which is the failure this is most likely to hit."""
    import requests

    try:
        r = requests.head(dataset.url, timeout=30, allow_redirects=True,
                          headers=HEADERS)
        if r.status_code >= 400 or "html" in r.headers.get("content-type", ""):
            r = requests.get(dataset.url, timeout=TIMEOUT, headers=HEADERS,
                             stream=True)
        ctype = r.headers.get("content-type", "?")
        size = r.headers.get("content-length", "?")
        ok = r.ok and "html" not in ctype
        return (f"{'ok  ' if ok else 'FAIL'} {dataset.id:<16} "
                f"HTTP {r.status_code}  {ctype}  {size} bytes")
    except Exception as exc:                            # noqa: BLE001
        return f"FAIL {dataset.id:<16} {type(exc).__name__}: {exc}"


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[1])
    ap.add_argument("--only", action="append", choices=sorted(DATASET_BY_ID),
                    help="refresh only these datasets; repeatable")
    ap.add_argument("--check", action="store_true",
                    help="resolve every URL and report; parse nothing")
    ap.add_argument("--from-file", type=pathlib.Path,
                    help="parse a local file instead of downloading; needs --only")
    ap.add_argument("--store", type=pathlib.Path, default=STORE)
    args = ap.parse_args(argv)

    wanted = [DATASET_BY_ID[i] for i in args.only] if args.only else DATASETS

    if args.check:
        results = [check(d) for d in wanted]
        print("\n".join(results))
        return 1 if any(r.startswith("FAIL") for r in results) else 0

    if args.from_file and len(wanted) != 1:
        print("--from-file needs exactly one --only dataset", file=sys.stderr)
        return 2

    failures = []
    for dataset in wanted:
        try:
            body = refresh(dataset, source=args.from_file, store=args.store)
        except Exception as exc:                        # noqa: BLE001
            # Deliberately broad: one dead URL must not stop the other four,
            # and the previous file stays where it is.
            failures.append((dataset.id, f"{type(exc).__name__}: {exc}"))
            print(f"FAIL {dataset.id}: {exc}", file=sys.stderr)
            continue
        print(f"ok   {dataset.id}: {body['observations']:,} observations, "
              f"latest {body['latest_period']}")
        for line in parse.summarise(
                [(f, a, p, v) for f, areas in body["values"].items()
                 for a, periods in areas.items() for p, v in periods.items()]):
            print(f"       {line}")

    if failures:
        print(f"\n{len(failures)} of {len(wanted)} dataset(s) failed. The "
              f"previous data for those is untouched.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
