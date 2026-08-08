"""Run both tests and print the numbers.

    python3 -m experiments.eia_library.report
"""

from .evaluate import format_score, summary
from .spatial import report as spatial_report


def main() -> None:
    print("=" * 72)
    print("SPIKE — is a shared EIA library safe to build? (item 11)")
    print("=" * 72)

    s = summary()
    print()
    print("TEST A — can identifiers be stripped without destroying findings?")
    print()
    print(format_score("  DEV (the redactor was written against this)", s["dev"]))
    print()
    print(format_score("  HELD OUT (written first, not consulted while building)",
                       s["heldout"]))
    print()
    print(spatial_report())
    print()
    print("=" * 72)
    print("Read experiments/eia_library/FINDINGS.md before quoting any of this.")
    print("=" * 72)


if __name__ == "__main__":
    main()
