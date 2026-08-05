"""
Schema migrations for the ingest tier.

The runner used to execute `CREATE TABLE IF NOT EXISTS` at startup, which
works exactly once — the first time. It cannot add a column, and adding a
column is precisely what tiling needs. So the schema now lives in numbered SQL
files that are applied in order and recorded, and the runner calls this
instead of its own DDL.

    python3 -m ingest.migrate --dsn postgresql://…            # apply
    python3 -m ingest.migrate --dsn postgresql://… --status   # show state

Two things are deliberately unusual here:

* **`{res}` is substituted per H3 resolution.** The fast tier is one table per
  resolution — `cell_stats_r7`, `cell_stats_r8` — because that is what
  BENCHMARK.md's two-tier result implies. A migration touching cell stats is
  therefore applied once per configured resolution, and the applied-record is
  keyed by (migration, resolution) so adding a third tier later replays the
  history for it alone.
* **Every statement is idempotent** (`IF NOT EXISTS`, `DROP CONSTRAINT IF
  EXISTS`). The applied-record is the fast path, not the safety net: a
  half-applied migration from a killed process must be re-runnable, and
  Postgres DDL is transactional, so each migration runs inside one.

This is small on purpose. It is a migration runner, not a migration framework:
no down-migrations, no autogeneration. A backfill is re-runnable, so the
recovery path for a bad migration is to write the next one.
"""

import argparse
import pathlib
import re
import sys
from typing import List, Optional, Sequence

MIGRATIONS = pathlib.Path(__file__).resolve().parent / "migrations"

# Which H3 tiers exist. Kept here rather than read from a manifest because the
# schema has to be complete before any manifest runs.
DEFAULT_RESOLUTIONS = (7, 8)

TRACKING = """
CREATE TABLE IF NOT EXISTS schema_migrations (
  name       text        NOT NULL,
  h3_res     int         NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (name, h3_res)
);
"""

# Applies to every resolution's table; anything else is global and recorded
# once under resolution 0.
_PER_RES = re.compile(r"\{res\}")


def migrations() -> List[pathlib.Path]:
    """Every migration, in the order their numeric prefix implies."""
    found = sorted(MIGRATIONS.glob("*.sql"))
    bad = [p.name for p in found if not re.match(r"^\d{3}_", p.name)]
    if bad:
        raise SystemExit(f"migrations must start with a 3-digit number: {bad}")
    return found


def _targets(sql: str, resolutions: Sequence[int]) -> List[int]:
    """Which resolutions a migration has to be applied for.

    A migration with no `{res}` in it is global — resolution 0 in the tracking
    table, applied once however many tiers exist.
    """
    return list(resolutions) if _PER_RES.search(sql) else [0]


def apply(conn, resolutions: Sequence[int] = DEFAULT_RESOLUTIONS,
          verbose: bool = True) -> int:
    """Apply every outstanding migration. Returns how many ran."""
    with conn.cursor() as cur:
        cur.execute(TRACKING)
    conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT name, h3_res FROM schema_migrations")
        done = {(name, res) for name, res in cur.fetchall()}

    ran = 0
    for path in migrations():
        sql = path.read_text()
        for res in _targets(sql, resolutions):
            if (path.name, res) in done:
                continue
            statement = sql.replace("{res}", str(res))
            with conn.cursor() as cur:
                cur.execute(statement)
                cur.execute(
                    "INSERT INTO schema_migrations (name, h3_res) VALUES (%s, %s) "
                    "ON CONFLICT DO NOTHING", (path.name, res))
            conn.commit()
            ran += 1
            if verbose:
                where = f" (res {res})" if res else ""
                print(f"  applied {path.name}{where}")
    return ran


def status(conn, resolutions: Sequence[int] = DEFAULT_RESOLUTIONS) -> List[tuple]:
    """(name, resolution, applied) for everything on disk."""
    with conn.cursor() as cur:
        cur.execute(TRACKING)
        conn.commit()
        cur.execute("SELECT name, h3_res FROM schema_migrations")
        done = {(name, res) for name, res in cur.fetchall()}

    out = []
    for path in migrations():
        for res in _targets(path.read_text(), resolutions):
            out.append((path.name, res, (path.name, res) in done))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().split("\n")[1])
    ap.add_argument("--dsn", required=True)
    ap.add_argument("--status", action="store_true",
                    help="report without applying anything")
    ap.add_argument("--h3-res", type=int, nargs="+", default=list(DEFAULT_RESOLUTIONS))
    args = ap.parse_args(argv)

    import psycopg

    with psycopg.connect(args.dsn, autocommit=False) as conn:
        if args.status:
            for name, res, applied in status(conn, args.h3_res):
                where = f" res {res}" if res else ""
                print(f"  {'✓' if applied else ' '} {name}{where}")
            return 0
        ran = apply(conn, args.h3_res)
        print(f"{ran} migration(s) applied." if ran else "Already up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
