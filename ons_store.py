"""
Serving the ONS spreadsheet data at request time.

`ons/job.py` downloads and parses the releases on a schedule and writes
`data/ons/<dataset>.json`. This reads those files. Between them they close the
gap `docs/OPEN-DATA.md` recorded: ONS publishes rents, earnings, affordability
and the census as spreadsheets rather than as per-area API endpoints, so there
was nothing for a live client to call and those factors stayed generated.

Three properties matter here, and all three come from where this runs:

* **No network, no database.** The files are read from disk and cached in the
  process. That is what lets these factors be real in the serverless function
  as well as locally — the same constraint that made `open_data.py` worth
  writing.
* **A missing file is not an error.** Until the job has run once there is no
  data, so the factors simply do not register and the catalogue keeps saying
  "generated". A half-populated store is normal and safe.
* **Every value carries its date.** ONS data is published in arrears and some
  of it annually, so a figure shown in 2026 may be from 2021. The release date
  and period travel with the number into the factor's provenance rather than
  being dropped at the door.

## What a local authority figure means for a drawn field

The same caveat as the Price Paid factors, and it has to stay visible: these
are published per local authority, so a 5-hectare AOI reports the figure for
the district containing it. That is real data and it is not a measurement of
the site. It is recorded in each factor's provenance note.
"""

from __future__ import annotations

import json
import pathlib
import threading
from typing import Any, Dict, List, Optional

ROOT = pathlib.Path(__file__).resolve().parent
STORE = ROOT / "data" / "ons"


def _dir(store: Optional[pathlib.Path]) -> pathlib.Path:
    """Resolved at call time, not bound as a default argument.

    A module-level default is captured when the function is defined, so a test
    or a deployment that repoints STORE would be silently ignored — the kind
    of bug where everything passes and nothing is being read.
    """
    return pathlib.Path(store) if store is not None else STORE

_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, Any]] = None


class OnsStoreError(RuntimeError):
    """The store cannot answer for this factor and area."""


def _load(store: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """Read every dataset file once per process.

    Deliberately not reloaded on change: the scheduled job writes these files
    and the serving process restarts on deploy, so watching them would be
    machinery for a case that does not arise.
    """
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE

        root = _dir(store)
        loaded: Dict[str, Any] = {"factors": {}, "meta": {}}
        if root.is_dir():
            for path in sorted(root.glob("*.json")):
                try:
                    body = json.loads(path.read_text())
                except (ValueError, OSError):
                    # A corrupt or half-written file costs its factors, not
                    # the process. The next scheduled run replaces it.
                    continue
                for factor, areas in (body.get("values") or {}).items():
                    loaded["factors"][factor] = areas
                    loaded["meta"][factor] = {
                        "dataset": body.get("dataset"),
                        "title": body.get("title"),
                        "publisher": body.get("publisher"),
                        "licence": body.get("licence"),
                        "page": body.get("page"),
                        "retrieved": body.get("retrieved"),
                        "latest_period": body.get("latest_period"),
                        "cadence": body.get("cadence"),
                    }
        _CACHE = loaded
        return _CACHE


def reset_cache() -> None:
    """For tests and for a job that has just rewritten the store."""
    global _CACHE
    with _LOCK:
        _CACHE = None


def available_factors(store: Optional[pathlib.Path] = None) -> List[str]:
    """Which factors the store can actually answer today.

    This is what decides whether a factor registers as real, so it reports
    what is present rather than what `ons/datasets.py` hopes for.
    """
    return sorted(_load(store)["factors"])


def factor_meta(factor: str, store: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    return dict(_load(store)["meta"].get(factor) or {})


def series(factor: str, area_code: str, steps: List[str],
           store: Optional[pathlib.Path] = None) -> List[Dict[str, Any]]:
    """One factor's series for one local authority, on the timeline's steps.

    Annual and one-off figures are carried forward across the months they
    cover and flagged `interpolated`, the same convention `open_data._static`
    uses — a census figure is a real observation of 2021 held across the
    timeline, and the flag is what stops a chart implying it was measured
    monthly.

    Months before the first published figure are gaps, never the first value
    carried backwards. "We do not know what the rent was in 2011" and "the
    rent in 2011 was the 2024 rent" are different claims.
    """
    data = _load(store)
    areas = data["factors"].get(factor)
    if not areas:
        raise OnsStoreError(f"no stored ONS data for {factor!r}")
    periods = areas.get(area_code)
    if not periods:
        raise OnsStoreError(
            f"{factor}: nothing published for area {area_code}")

    monthly = {p: v for p, v in periods.items() if len(p) == 7}
    annual = {p: v for p, v in periods.items() if len(p) == 4}
    first_year = min(annual) if annual else None

    out: List[Dict[str, Any]] = []
    for step in steps:
        year = step[:4]
        exact = monthly.get(step)
        if exact is not None:
            out.append({"t": step, "value": exact, "valid_fraction": 1.0,
                        "interpolated": False})
            continue

        value = annual.get(year)
        carried = False
        if value is None and annual:
            # The most recent published year at or before this step. A one-off
            # release like the census has a single year and applies forward
            # from it, not backwards before it.
            earlier = [y for y in annual if y <= year]
            if earlier:
                value = annual[max(earlier)]
                carried = True
            elif first_year is not None and year < first_year:
                value = None

        if value is None:
            out.append({"t": step, "value": None, "valid_fraction": 0.0,
                        "interpolated": False})
        else:
            out.append({"t": step, "value": value, "valid_fraction": 1.0,
                        "interpolated": carried or bool(annual)})
    return out


def coverage(store: Optional[pathlib.Path] = None) -> Dict[str, Any]:
    """A summary for the docs and for `scripts/audit_catalogue.py`."""
    data = _load(store)
    return {
        factor: {
            "authorities": len(areas),
            "periods": len({p for a in areas.values() for p in a}),
            **factor_meta(factor, store),
        }
        for factor, areas in sorted(data["factors"].items())
    }
