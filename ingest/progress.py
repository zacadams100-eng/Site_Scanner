"""
What has already been ingested, so a backfill resumes instead of restarting.

A national run at 10 m is 180 timesteps x 48 tiles x 2 resolutions — over
17,000 units of work, hours of compute, and a certainty that something will
interrupt it. The unit of resumption has to be the tile: marking a whole
timestep done after its first tile finishes would make a resumed run skip 47
tiles it never processed, silently, leaving a table that looks complete.

Two stores, one interface:

* `PostgresProgress` — the real one. The mark is written in the same
  transaction as the tile's rows, so a tile is either fully loaded and
  recorded, or neither. That is what stops a killed process leaving
  half-merged statistics that a retry would then double-count.
* `FileProgress` — for runs with no database, which is every COG-only run and
  every test. Same keys, same semantics, a JSON file next to the output.

Both are keyed by `(dataset, timestep, tile, h3_res)` and both record the tile
grid, because tile ids are positions in a grid and resuming across a change of
grid is not resumption.
"""

import json
import os
import pathlib
import tempfile
from typing import Dict, Optional, Set, Tuple

Key = Tuple[str, str, str, int]        # dataset, timestep, tile, h3_res


class Progress:
    """Interface. `done()` decides whether work is skipped; `mark()` records
    it; `grid_for()` reports which tiling produced the existing records."""

    def done(self, dataset: str, t: str, tile: str, res: int) -> bool:
        raise NotImplementedError

    def mark(self, dataset: str, t: str, tile: str, res: int,
             n_cells: int, grid: str) -> None:
        raise NotImplementedError

    def grid_for(self, dataset: str) -> Optional[str]:
        raise NotImplementedError

    def close(self) -> None:
        pass


class FileProgress(Progress):
    """A JSON file. Written atomically after every mark.

    Rewriting the whole file per tile is fine at this scale — 17,000 records
    is a few hundred KB — and it means an interrupted write cannot corrupt the
    record, which a partial append could.
    """

    def __init__(self, path: pathlib.Path):
        self.path = pathlib.Path(path)
        self._records: Dict[str, dict] = {}
        if self.path.exists():
            try:
                self._records = json.loads(self.path.read_text())
            except (ValueError, OSError):
                # A corrupt progress file must not stop a backfill: the worst
                # case is redoing work, and every stage is idempotent.
                self._records = {}

    @staticmethod
    def _key(dataset: str, t: str, tile: str, res: int) -> str:
        return f"{dataset}\t{t}\t{tile}\t{res}"

    def done(self, dataset, t, tile, res) -> bool:
        return self._key(dataset, t, tile, res) in self._records

    def mark(self, dataset, t, tile, res, n_cells, grid) -> None:
        self._records[self._key(dataset, t, tile, res)] = {
            "n_cells": n_cells, "grid": grid}
        self._flush()

    def grid_for(self, dataset: str) -> Optional[str]:
        prefix = f"{dataset}\t"
        for key, rec in self._records.items():
            if key.startswith(prefix):
                return rec.get("grid")
        return None

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(self._records, fh)
            os.replace(tmp, self.path)
        except BaseException:
            pathlib.Path(tmp).unlink(missing_ok=True)
            raise


class PostgresProgress(Progress):
    """The real store. Reads the whole progress set once, then answers from
    memory — a backfill asks `done()` 17,000 times and each one being a round
    trip would add minutes for nothing."""

    def __init__(self, conn):
        self.conn = conn
        self._done: Set[Key] = set()
        self._grids: Dict[str, str] = {}
        with conn.cursor() as cur:
            cur.execute("SELECT dataset_id, t, tile, h3_res, grid FROM ingest_progress")
            for dataset, t, tile, res, grid in cur.fetchall():
                self._done.add((dataset, t, tile, int(res)))
                self._grids.setdefault(dataset, grid)

    def done(self, dataset, t, tile, res) -> bool:
        return (dataset, t, tile, int(res)) in self._done

    def mark(self, dataset, t, tile, res, n_cells, grid) -> None:
        """Recorded, not committed. The caller commits once per tile, so the
        mark and the tile's statistics land together or not at all."""
        with self.conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ingest_progress
                     (dataset_id, t, h3_res, tile, grid, n_cells)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (dataset_id, t, h3_res, tile)
                   DO UPDATE SET n_cells = EXCLUDED.n_cells,
                                 grid = EXCLUDED.grid,
                                 done_at = now()""",
                (dataset, t, int(res), tile, grid, n_cells))
        self._done.add((dataset, t, tile, int(res)))
        self._grids.setdefault(dataset, grid)

    def grid_for(self, dataset: str) -> Optional[str]:
        return self._grids.get(dataset)
