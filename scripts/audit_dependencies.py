#!/usr/bin/env python3
"""
Which third-party code ships, and under what licence.

    python3 scripts/audit_dependencies.py            # summary
    python3 scripts/audit_dependencies.py --write     # regenerate docs/IP_AUDIT.md

Two questions that get conflated and must not be:

**Is it copyleft?** and **does it reach a customer?** A GPL build tool is not a
licensing problem; a GPL library inside the bundle a customer downloads is a
different conversation entirely.

Two traps this exists to avoid, both of which caught the first pass by hand:

- `importlib.metadata` sees **everything installed in the environment**,
  including Ubuntu's own Python packages. A naive scan reports `python-apt`
  (GPL) and four LGPL `launchpadlib` packages as dependencies of this product.
  They are not. This walks the transitive closure of `requirements.txt`
  instead, which found exactly one copyleft package where the naive scan
  found five.
- A package being a `devDependency` is not the same as it not shipping — a
  *transitive* runtime dependency is neither. `@turf/jsts` is EPL-licensed and
  reached through `@turf/turf`, which is a runtime dependency. The only honest
  test is to look in the built bundle, which this does.
"""

import argparse
import glob
import importlib.metadata as md
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "IP_AUDIT.md"

COPYLEFT = ("GPL", "LGPL", "AGPL", "MPL", "Mozilla", "EPL", "Eclipse", "CDDL")


def python_closure() -> set:
    """Only what `requirements.txt` actually pulls in."""
    roots = set()
    for f in ("requirements.txt", "api/requirements.txt"):
        path = ROOT / f
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                roots.add(re.split(r"[<>=!\[]", line)[0].strip().lower())

    seen, stack = set(), list(roots)
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        try:
            dist = md.distribution(name)
        except Exception:                                   # noqa: BLE001
            continue
        for req in dist.requires or []:
            # Skip optional extras — they are not installed unless asked for.
            if ";" in req and "extra" in req.split(";", 1)[1]:
                continue
            stack.append(re.split(r"[<>=!\[ ;(]", req)[0].strip().lower())
    return seen


def licence_of(name: str) -> str:
    try:
        dist = md.distribution(name)
    except Exception:                                       # noqa: BLE001
        return "not installed"
    classifiers = [c for c in (dist.metadata.get_all("Classifier") or [])
                   if "License ::" in c]
    if classifiers:
        return classifiers[0].split("::")[-1].strip()
    return (dist.metadata["License"] or "UNDECLARED").splitlines()[0][:60]


def npm_packages() -> dict:
    out = {}
    for f in (glob.glob(str(ROOT / "web/node_modules/*/package.json"))
              + glob.glob(str(ROOT / "web/node_modules/@*/*/package.json"))):
        try:
            d = json.loads(pathlib.Path(f).read_text())
        except Exception:                                   # noqa: BLE001
            continue
        name = d.get("name")
        if not name:
            continue
        lic = d.get("license")
        if not isinstance(lic, str):
            legacy = d.get("licenses")
            lic = (legacy[0].get("type") if isinstance(legacy, list) and legacy
                   else "UNDECLARED")
        out[name] = lic or "UNDECLARED"
    return out


def in_bundle(needles) -> dict:
    """Does this actually reach the browser? The only test that settles it."""
    bundles = glob.glob(str(ROOT / "web/dist/assets/*.js"))
    if not bundles:
        return {n: None for n in needles}          # None = no build to check
    blob = "".join(pathlib.Path(b).read_text(errors="ignore") for b in bundles)
    return {n: (n in blob) for n in needles}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    py = sorted(python_closure())
    py_lic = {n: licence_of(n) for n in py}
    py_copyleft = {n: l for n, l in py_lic.items()
                   if any(k in l for k in COPYLEFT)}

    npm = npm_packages()
    npm_copyleft = {n: l for n, l in npm.items()
                    if any(k in l for k in COPYLEFT)}
    ships = in_bundle(list(npm_copyleft))

    print(f"Python: {len(py)} packages in the requirements closure, "
          f"{len(py_copyleft)} copyleft")
    for n, l in sorted(py_copyleft.items()):
        print(f"  {n:<22} {l}")
    print(f"\nnpm: {len(npm)} packages installed, "
          f"{len(npm_copyleft)} copyleft-ish")
    for n, l in sorted(npm_copyleft.items()):
        state = ships.get(n)
        mark = "SHIPS" if state else ("not in bundle" if state is False
                                      else "no build to check")
        print(f"  {n:<38} {l:<24} {mark}")

    if args.write:
        write_doc(py, py_lic, py_copyleft, npm, npm_copyleft, ships)
        print(f"\nWrote {OUT.relative_to(ROOT)}")
    return 0


def write_doc(py, py_lic, py_copyleft, npm, npm_copyleft, ships) -> None:
    import collections
    import datetime as dt

    npm_counts = collections.Counter(npm.values())
    py_counts = collections.Counter(py_lic.values())

    lines = [
        "# Dependency & IP audit",
        "",
        "<!-- GENERATED by scripts/audit_dependencies.py --write -->",
        "",
        f"Generated {dt.date.today().isoformat()}. **Not legal advice.** "
        "Licence strings are what each package declares about itself; no "
        "licence text was fetched or read.",
        "",
        "## The two questions, kept apart",
        "",
        "**Is it copyleft?** and **does it reach a customer?** A GPL build "
        "tool is not a licensing problem. A GPL library inside the bundle a "
        "customer downloads is a different conversation.",
        "",
        "## Python",
        "",
        f"{len(py)} packages in the transitive closure of `requirements.txt` "
        "and `api/requirements.txt`.",
        "",
        "| Licence | Packages |",
        "| --- | ---: |",
    ]
    for lic, n in py_counts.most_common():
        lines.append(f"| {lic} | {n} |")

    lines += ["", "### Copyleft in the Python closure", ""]
    if py_copyleft:
        lines.append("| Package | Licence | Note |")
        lines.append("| --- | --- | --- |")
        for n, l in sorted(py_copyleft.items()):
            note = ("CA certificate bundle, used unmodified. MPL-2.0 is "
                    "file-level weak copyleft; obligations attach to modified "
                    "MPL files, and none are modified here."
                    if n == "certifi" else "LEGAL REVIEW REQUIRED")
            lines.append(f"| `{n}` | {l} | {note} |")
    else:
        lines.append("None.")

    lines += [
        "",
        "> **A naive scan reports five.** `importlib.metadata` sees every "
        "package installed in the environment, including Ubuntu's own — "
        "`python-apt` (GPL), `PyGObject`, `launchpadlib`, `lazr.restfulclient`,"
        " `wadllib` (LGPL). None is a dependency of this product. Walking the "
        "requirements closure is what tells them apart, and the difference "
        "between one copyleft dependency and five is the difference between a "
        "footnote and a meeting.",
        "",
        "## npm",
        "",
        f"{len(npm)} packages installed.",
        "",
        "| Licence | Packages |",
        "| --- | ---: |",
    ]
    for lic, n in npm_counts.most_common(10):
        lines.append(f"| {lic} | {n} |")

    lines += ["", "### Copyleft-ish, and whether it ships", "",
              "| Package | Licence | In the built bundle? |",
              "| --- | --- | --- |"]
    for n, l in sorted(npm_copyleft.items()):
        state = ships.get(n)
        mark = ("**yes — ships to the browser**" if state
                else ("no — not in the bundle" if state is False
                      else "unknown, no build present"))
        lines.append(f"| `{n}` | {l} | {mark} |")

    lines += [
        "",
        "### The fonts, which do ship",
        "",
        "`@fontsource/ibm-plex-sans`, `@fontsource/ibm-plex-mono` and "
        "`@fontsource/inter` are **SIL Open Font License 1.1** and are served "
        "to every visitor.",
        "",
        "OFL-1.1 permits commercial use and embedding. The clause that "
        "matters is **Reserved Font Name**: a modified version may not be "
        "distributed under the original name. This project embeds them "
        "unmodified, so the condition appears satisfied — but the licence "
        "text has not been read, so: **LEGAL REVIEW REQUIRED** before "
        "commercial launch, and do not rename or subset-and-rename the fonts.",
        "",
        "### `jsts` — checked rather than assumed",
        "",
        "`@turf/jsts` is EPL/EDL-licensed and is a **transitive runtime** "
        "dependency, reached through `@turf/turf`. Being a transitive rather "
        "than a direct dependency says nothing about whether it ships, so the "
        "built bundle was searched directly. It is not there — tree-shaken "
        "out. Re-check after any change to how geometry is handled.",
        "",
        "## Not covered",
        "",
        "- Licence *texts*. Only what each package declares about itself.",
        "- Runtime third parties that are not packages: map tiles, the glyph "
        "host, the geocoder. See `LEGAL_RISK_REGISTER.md` L17.",
        "- Whether a declared licence is correct. `splaytree-ts` declares "
        "`BDS-3-Clause`, which is a typo for BSD-3-Clause and a reminder that "
        "these strings are self-reported.",
        "",
    ]
    OUT.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
