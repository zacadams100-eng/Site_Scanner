#!/usr/bin/env python3
"""
Everything that needs a real internet connection, in one command.

    python3 scripts/verify.py

This exists because the verification never happened, and the reason it never
happened was not that it was hard. It was that it was *scattered*: four
scripts, four sets of output, four judgements about what to do next, and no
single answer to the only question that matters — how much of this catalogue
has ever been checked against reality.

That question has one number, and it has been **1** since NDVI. This script's
job is to move it.

## What it runs

    1  open data       22 factors against five government APIs
    2  planning        the flood-zone attribute name, which is a live guess
    3  ONS             whether five release URLs still resolve
    4  Earth Engine    27 factors, only if credentials are present

Each one already existed. Nothing here re-implements a check; it runs them,
collects what they found, and prints one scoreboard with an explicit next
action against every failure.

## What it writes

`verify-report.md` in the repo root — a summary you can paste straight back
into a coding session. That is deliberate: the results are useless sitting in
a terminal you close, and re-typing "police.uk returned a 500" from memory is
how a real finding becomes a vague one.

## Exit codes

    0   everything checked passed
    1   something is genuinely wrong and the report says what
    2   nothing could be checked — no network at all

The difference between 1 and 2 matters. "Twelve factors are broken" and "you
are offline" are not the same result, and treating them the same is how a
train journey turns into a to-do list of imaginary bugs.
"""

import argparse
import datetime as dt
import io
import contextlib
import pathlib
import subprocess
import sys
import time
from typing import List, NamedTuple, Optional

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

REPORT = ROOT / "verify-report.md"


class Outcome(NamedTuple):
    key: str
    title: str
    status: str          # pass | fail | offline | skipped
    seconds: float
    detail: str
    fix: str


def _run(argv: List[str], timeout: int = 600) -> tuple:
    """Run one check as a subprocess.

    Subprocess rather than import, for once. These scripts call `sys.exit`,
    mutate module-level registries and print freely; running four of them in
    one interpreter would have the first one's state decide the third one's
    result. A process boundary makes each answer independent, which is the
    whole point of a scoreboard.
    """
    t0 = time.perf_counter()
    try:
        p = subprocess.run(argv, cwd=str(ROOT), capture_output=True,
                           text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or ""), time.perf_counter() - t0
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s", time.perf_counter() - t0
    except FileNotFoundError as e:
        return 127, str(e), time.perf_counter() - t0


# Wording that means "the network refused", across the several libraries these
# scripts use. Checked so a train-journey run does not read as a broken repo.
_OFFLINE = (
    "proxyerror", "tunnel connection failed", "failed to establish",
    "name or service not known", "temporary failure in name resolution",
    "connection refused", "network is unreachable", "unreachable",
    "max retries exceeded", "certificate verify failed",
)


def _looks_offline(output: str) -> bool:
    low = output.lower()
    return any(s in low for s in _OFFLINE)


def _tail(output: str, lines: int = 200) -> str:
    """Keep the output, not a glimpse of it.

    This was 14 lines, which is a sensible default for a terminal and the
    wrong one for a file that exists to be pasted back. The open-data check
    reports 24 factors one per line, so the first ten — every planning
    designation — scrolled off, and the report showed only prices and police.
    A reader could not tell whether the designations had passed, failed or
    never run, which is the one thing the report is for.
    """
    kept = [ln for ln in output.strip().splitlines() if ln.strip()]
    if len(kept) <= lines:
        return "\n".join(kept)
    # Trim from the middle rather than the top: the first lines say what was
    # checked and the last say how it ended, and both matter more than the run
    # of `ok` in between.
    head, tail = kept[: lines // 2], kept[-(lines // 2):]
    return "\n".join(head + [f"… {len(kept) - lines} lines omitted …"] + tail)


def check_open_data() -> Outcome:
    code, out, secs = _run([sys.executable, "scripts/check_open_data.py"])
    if _looks_offline(out):
        return Outcome("open-data", "Open data (22 factors)", "offline", secs,
                       _tail(out, 4),
                       "No route to the government APIs from this machine.")
    return Outcome(
        "open-data", "Open data (22 factors)",
        "pass" if code == 0 else "fail", secs, _tail(out),
        "Open the failing source's docs and fix its function in open_data.py. "
        "Each check names the factor and what came back.")


def check_flood_attribute() -> Outcome:
    """The single highest-value check in the file.

    `flood_zone2_pct` and `flood_zone3_pct` filter on an attribute name taken
    from a published schema and never seen in a live response. If it is wrong
    they fall back to labelled demo data — deliberately, rather than reporting
    0% flood risk on a floodplain — and this says what to change it to.
    """
    code, out, secs = _run([sys.executable, "scripts/discover_planning_datasets.py",
                            "--attributes", "flood-risk-zone"])
    if code == 2 or _looks_offline(out):
        return Outcome("flood", "Flood-zone attribute", "offline", secs,
                       _tail(out, 4), "No route to planning.data.gov.uk.")
    return Outcome(
        "flood", "Flood-zone attribute",
        "pass" if code == 0 else "fail", secs, _tail(out),
        "The output lists the attribute names actually returned. Put the right "
        "one in PLANNING_DATASETS in open_data.py — it is one string.")


def check_ons() -> Outcome:
    code, out, secs = _run([sys.executable, "-m", "ons.job", "--check"])
    if _looks_offline(out):
        return Outcome("ons", "ONS release URLs", "offline", secs, _tail(out, 4),
                       "No route to ONS.")
    return Outcome(
        "ons", "ONS release URLs", "pass" if code == 0 else "fail", secs,
        _tail(out),
        "ONS rotates these on every release, so expect some to have moved. "
        "Each spec in ons/datasets.py carries a `page` link — open it and copy "
        "the current file URL. Then run `python3 -m ons.job` to ingest.")


def check_earth_engine() -> Outcome:
    """Earth Engine, if it can start at all.

    The variable checked here is `GOOGLE_APPLICATION_CREDENTIALS_JSON`,
    because that is the one `app.py` actually reads. The first version looked
    for `EE_SERVICE_ACCOUNT_JSON` and a key file on disk, found the key file,
    decided credentials were present, ran the check and reported a red FAIL —
    when the real answer was "you have a key, you just have not loaded it".
    A setup step reported as a data-layer failure is a wasted hour.
    """
    import os
    if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
        has_key = list(pathlib.Path.home().glob("ee-backend/*.json"))
        if has_key:
            return Outcome(
                "earth-engine", "Earth Engine (27 factors)", "skipped", 0.0,
                "A service-account key is on disk but not loaded into the "
                "environment.",
                "Run `source ./setup.sh` (with `source`, not `./setup.sh`) "
                "and then re-run this. That loads the key and sets the "
                "project id.")
        return Outcome(
            "earth-engine", "Earth Engine (27 factors)", "skipped", 0.0,
            "No service-account credentials found.",
            "This one runs in CI on every push once EE_SERVICE_ACCOUNT_JSON and "
            "EE_PROJECT_ID are set as repository secrets — you do not have to "
            "run it by hand. Check the Actions tab instead.")

    code, out, secs = _run([sys.executable, "scripts/check_real_factors.py", "2024"])
    if _looks_offline(out):
        return Outcome("earth-engine", "Earth Engine (27 factors)", "offline",
                       secs, _tail(out, 4), "No route to Earth Engine.")
    return Outcome(
        "earth-engine", "Earth Engine (27 factors)",
        "pass" if code == 0 else "fail", secs, _tail(out),
        "A failure here names the factor and what was wrong with its values. "
        "Read it as a data-layer bug, not a network one.")


CHECKS = [check_open_data, check_flood_attribute, check_ons, check_earth_engine]

MARK = {"pass": "PASS", "fail": "FAIL", "offline": "----", "skipped": "skip"}


def catalogue_state() -> str:
    """The one number this whole exercise is about.

    Counts Earth Engine's factors from its coverage table rather than by
    installing the module, because `ee_series` imports `ee` lazily but
    `install` does not — so a machine without the Earth Engine package would
    report 24 real factors instead of 51 and make the headline number wrong in
    the one place it is supposed to be right.
    """
    try:
        import catalog
        import routes_catalog
        import open_data
        open_data.install(routes_catalog.REAL_SERIES, routes_catalog.REAL_SOURCES)
        verified = sum(1 for v in routes_catalog.REAL_SOURCES.values()
                       if v.get("status") == "verified")
        real = set(routes_catalog.REAL_SERIES)

        try:
            import ee_series
            real |= set(ee_series.FACTOR_COVERAGE)
            verified += len(ee_series._VERIFIED_EE & set(ee_series.FACTOR_COVERAGE))
        except Exception:
            pass

        total = len(catalog.FACTORS)
        return (f"{len(real)} of {total} factors real "
                f"({100*len(real)/total:.0f}%), of which {verified} verified "
                f"against a live service")
    except Exception as e:                      # pragma: no cover - diagnostic
        return f"could not read the catalogue: {e.__class__.__name__}"


def write_report(results: List[Outcome], state: str) -> None:
    lines = [
        "# Verification report",
        "",
        f"Run {dt.datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"**Catalogue before this run:** {state}",
        "",
        "Paste this whole file into a coding session — the detail below is what",
        "is needed to fix anything that failed.",
        "",
        "| Check | Result | Time |",
        "| --- | --- | ---: |",
    ]
    for r in results:
        lines.append(f"| {r.title} | {r.status} | {r.seconds:.0f}s |")

    for r in results:
        if r.status in ("pass", "skipped"):
            continue
        lines += ["", f"## {r.title} — {r.status}", "", "```", r.detail, "```",
                  "", f"**Next:** {r.fix}"]

    passed = [r for r in results if r.status == "pass"]
    if passed:
        lines += ["", "## Passed", ""]
        lines += [f"- {r.title}" for r in passed]
        lines += ["",
                  "For each of these, the factors it covers can move from",
                  "`written` to `verified`. That is the number worth changing."]

    REPORT.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", choices=["open-data", "flood", "ons", "earth-engine"],
                    help="run a single check")
    args = ap.parse_args()

    state = catalogue_state()
    print("=" * 68)
    print("Site Scanner — verification")
    print("=" * 68)
    print(f"\nBefore this run: {state}\n")

    results: List[Outcome] = []
    for fn in CHECKS:
        probe = fn.__name__.replace("check_", "").replace("_", "-")
        if args.only and probe != args.only:
            continue
        print(f"  running {probe}…", flush=True)
        r = fn()
        results.append(r)
        print(f"  [{MARK[r.status]}] {r.title}  ({r.seconds:.0f}s)")

    print("\n" + "-" * 68)
    offline = [r for r in results if r.status == "offline"]
    failed = [r for r in results if r.status == "fail"]
    passed = [r for r in results if r.status == "pass"]

    if offline and not passed and not failed:
        print("Nothing could be checked — every host was unreachable.")
        print("This machine has no route to the outside world; it is not a")
        print("repository problem. Try again on an ordinary connection.")
        write_report(results, state)
        print(f"\nWritten to {REPORT.relative_to(ROOT)}")
        return 2

    print(f"{len(passed)} passed, {len(failed)} failed"
          + (f", {len(offline)} unreachable" if offline else ""))

    if failed:
        print("\nWhat to do next, in order:\n")
        for i, r in enumerate(failed, 1):
            print(f"  {i}. {r.title}\n     {r.fix}\n")

    write_report(results, state)
    print(f"Full detail written to {REPORT.relative_to(ROOT)}")
    print("Paste that file into a coding session and the fixes can be made "
          "from it.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
