"""
Cutting an extent into tiles the machine can actually hold.

England at 10 m is 63,000 x 66,200 pixels — 4.2 billion, 16.7 GB as float32
before the COG writer takes its copy. There is no national run at full
resolution without tiling, which is why `docs/INGEST-BENCHMARK.md` Result 7
called this the largest gap in the pipeline.

Three properties matter, and all three are about resuming rather than about
speed:

* **Deterministic.** The same manifest and window must produce the same tiles
  in the same order every time, or a resumed run cannot know which tile ids
  the previous run meant. Nothing here consults the filesystem, the clock or
  the environment.
* **Self-identifying.** A tile carries the grid it came from (`8x6/r02c05`).
  Change the pixel budget and the grid changes, and a run against old progress
  records is refused rather than silently mixing 6-tile work with 48-tile
  work — which would look complete and be full of holes.
* **Exactly covering, never overlapping.** Tiles partition the extent to the
  pixel. Overlap would double-count pixels in the merge; a gap would lose a
  strip of the country. Row and column edges are computed by cumulative pixel
  counts rather than by repeated floating-point addition, so the last tile
  ends exactly on the extent's edge.
"""

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

# How many pixels one tile may hold. 25 M float32 is 100 MB for the array, and
# quantisation takes a float64 copy on the way out, so the working set peaks
# around 300 MB — comfortable on a 2 GB worker and roughly the size the Surrey
# benchmark ran at (28.2 M), which is the only size anything here is measured
# against.
TILE_PIXEL_BUDGET = 25_000_000


@dataclass(frozen=True)
class Tile:
    """One piece of an extent, and where it sits in the grid."""
    id: str                                  # 'r02c05', or '-' when untiled
    grid: str                                # '8x6', or '1x1'
    row: int
    col: int
    bbox: Tuple[float, float, float, float]
    width: int
    height: int

    @property
    def pixels(self) -> int:
        return self.width * self.height

    @property
    def untiled(self) -> bool:
        return self.id == UNTILED_ID


# What a whole-extent run records. It is a real tile id rather than a null,
# because it has to sit in a primary key, and rows written before tiling
# existed carry it too — see ingest/migrations/002_tile_progress.sql.
UNTILED_ID = "-"
UNTILED_GRID = "1x1"


def _edges(lo: float, hi: float, total_px: int, pieces: int) -> List[Tuple[float, int]]:
    """Split [lo, hi] into `pieces`, returning (coordinate, pixel index) pairs.

    Pixel counts are apportioned first and coordinates derived from them, not
    the other way round: a tile is a whole number of pixels, and deriving the
    count from a rounded coordinate is how a one-pixel seam appears between
    two tiles that are individually correct.
    """
    out = []
    for i in range(pieces + 1):
        px = round(total_px * i / pieces)
        out.append((lo + (hi - lo) * px / total_px, px))
    return out


def plan(bbox: Sequence[float], width: int, height: int,
         budget: int = TILE_PIXEL_BUDGET) -> List[Tile]:
    """Tile an extent of `width` x `height` pixels into pieces within `budget`.

    Returns a single tile marked untiled when the whole extent already fits,
    so a Surrey-sized run behaves exactly as it did before tiling existed and
    its progress records stay comparable.
    """
    west, south, east, north = bbox
    total = width * height
    if total <= budget:
        return [Tile(UNTILED_ID, UNTILED_GRID, 0, 0,
                     (west, south, east, north), width, height)]

    # Aim for square-ish tiles: splitting only one axis makes long thin strips,
    # which read badly out of a COG and give the aggregator a poor ratio of
    # H3-cell boundary to interior.
    import math

    pieces = math.ceil(total / budget)
    cols = max(1, round(math.sqrt(pieces * width / max(1, height))))
    rows = max(1, math.ceil(pieces / cols))
    while (width / cols) * (height / rows) > budget:
        # Grow whichever axis is currently coarser, so tiles stay square-ish.
        if width / cols >= height / rows:
            cols += 1
        else:
            rows += 1

    grid = f"{cols}x{rows}"
    xs = _edges(west, east, width, cols)
    ys = _edges(north, south, height, rows)      # north to south: row 0 on top

    tiles: List[Tile] = []
    for r in range(rows):
        for c in range(cols):
            (x0, px0), (x1, px1) = xs[c], xs[c + 1]
            (y0, py0), (y1, py1) = ys[r], ys[r + 1]
            tiles.append(Tile(
                id=f"r{r:02d}c{c:02d}", grid=grid, row=r, col=c,
                bbox=(x0, y1, x1, y0),           # west, south, east, north
                width=px1 - px0, height=py1 - py0,
            ))
    return tiles


def describe(tiles: Sequence[Tile]) -> str:
    if len(tiles) == 1 and tiles[0].untiled:
        return f"one pass ({tiles[0].pixels / 1e6:.1f} M px)"
    biggest = max(t.pixels for t in tiles)
    return (f"{len(tiles)} tiles on a {tiles[0].grid} grid, "
            f"largest {biggest / 1e6:.1f} M px")


def check_grid(tiles: Sequence[Tile], recorded: Optional[str]) -> None:
    """Refuse to resume across a change of tiling.

    Tile ids are positions in a grid, so `r02c05` of an 8x6 grid and `r02c05`
    of a 12x9 grid are different pieces of the country. Resuming one against
    the other's progress would skip work that was never done and produce a
    table that looks complete. There is no safe automatic reconciliation: the
    honest options are to finish with the old grid or to start again, and the
    error says so.
    """
    if recorded is None:
        return
    current = tiles[0].grid
    if recorded != current:
        raise SystemExit(
            f"This run tiles the extent as {current}, but the recorded "
            f"progress was made with {recorded}. Tile ids mean different "
            f"areas under different grids, so resuming would silently skip "
            f"work.\n"
            f"Either re-run with the pixel budget that produced {recorded} "
            f"(--tile-pixels), or clear this dataset's rows from "
            f"ingest_progress and start the backfill again."
        )
