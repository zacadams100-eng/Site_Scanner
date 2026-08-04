"""
Tiling, and the two properties that make it safe to run nationally.

A national run at 10 m is 4.2 billion pixels per timestep and cannot happen in
one pass (docs/INGEST-BENCHMARK.md Result 7). Cutting it up introduces exactly
two ways to be wrong, and both are silent:

1. **The seams.** An H3 cell on a tile boundary is aggregated once per tile it
   touches, over only that tile's pixels. If those partials are overwritten
   rather than merged, every cell on every tile edge in the country holds
   whichever sliver was written last — a wrong number that looks like a right
   one.
2. **The resume.** If progress is recorded per timestep rather than per tile,
   a run that dies mid-timestep comes back, sees the timestep marked done, and
   skips every tile it never processed. The table ends up looking complete.

Everything here is offline: no database, no network. The Postgres merge is the
same arithmetic as `merge_stats` and is checked against it in
`test_ingest_postgres.py` when a server is available.
"""

import json

import numpy as np
import pytest

from ingest import tiling
from ingest.aggregate import CellStat, aggregate_array, merge_stats
from ingest.cog import synthetic_raster
from ingest.progress import FileProgress

SURREY = (-0.85, 51.07, 0.06, 51.47)


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------
def test_an_extent_that_fits_is_left_alone():
    """A Surrey-sized run must behave exactly as it did before tiling existed,
    so its benchmark numbers stay comparable."""
    tiles = tiling.plan(SURREY, 6338, 4453, budget=50_000_000)
    assert len(tiles) == 1
    assert tiles[0].untiled and tiles[0].grid == "1x1"
    assert tiles[0].bbox == SURREY


def test_a_national_extent_is_cut_into_tiles_within_budget():
    tiles = tiling.plan((-6.42, 49.86, 1.77, 55.81), 55078, 66235,
                        budget=25_000_000)
    assert len(tiles) > 100
    assert all(t.pixels <= 25_000_000 for t in tiles)
    assert len({t.id for t in tiles}) == len(tiles), "tile ids must be unique"


def test_tiles_cover_the_extent_exactly_and_never_overlap():
    """Overlap double-counts pixels in the merge; a gap loses a strip of the
    country. Both are checked in pixels, because that is the unit the seam
    would appear in."""
    tiles = tiling.plan(SURREY, 6338, 4453, budget=4_000_000)
    assert len(tiles) > 1

    assert sum(t.pixels for t in tiles) == 6338 * 4453

    cols = sorted({t.col for t in tiles})
    rows = sorted({t.row for t in tiles})
    for r in rows:                       # each row spans the full width
        row = sorted((t for t in tiles if t.row == r), key=lambda t: t.col)
        assert row[0].bbox[0] == pytest.approx(SURREY[0])
        assert row[-1].bbox[2] == pytest.approx(SURREY[2])
        for a, b in zip(row, row[1:]):
            assert a.bbox[2] == pytest.approx(b.bbox[0]), "gap or overlap in x"
    for c in cols:                       # each column spans the full height
        col = sorted((t for t in tiles if t.col == c), key=lambda t: t.row)
        assert col[0].bbox[3] == pytest.approx(SURREY[3])
        assert col[-1].bbox[1] == pytest.approx(SURREY[1])
        for a, b in zip(col, col[1:]):
            assert a.bbox[1] == pytest.approx(b.bbox[3]), "gap or overlap in y"


def test_the_plan_is_deterministic():
    """A resumed run recomputes the grid from scratch. If it came out
    differently, the recorded tile ids would refer to other places."""
    a = tiling.plan(SURREY, 6338, 4453, budget=4_000_000)
    b = tiling.plan(SURREY, 6338, 4453, budget=4_000_000)
    assert [t.id for t in a] == [t.id for t in b]
    assert [t.bbox for t in a] == [t.bbox for t in b]


def test_resuming_across_a_changed_grid_is_refused():
    """r02c05 of an 8x6 grid is not r02c05 of a 12x9 grid. Continuing anyway
    would skip work that was never done, and there is no safe automatic
    reconciliation."""
    tiles = tiling.plan(SURREY, 6338, 4453, budget=4_000_000)
    tiling.check_grid(tiles, tiles[0].grid)          # same grid is fine
    tiling.check_grid(tiles, None)                   # nothing recorded is fine
    with pytest.raises(SystemExit) as exc:
        tiling.check_grid(tiles, "99x99")
    assert "silently skip" in str(exc.value)


# --------------------------------------------------------------------------
# The seams
# --------------------------------------------------------------------------
def test_the_synthetic_surface_does_not_depend_on_the_window():
    """The property the equivalence test below rests on: a tile is a view of
    one global surface, not its own random field. Without this, tiled and
    untiled runs produce different pixels and nothing can be compared."""
    whole, _ = synthetic_raster(SURREY, 900, 400, seed=11)
    west = (SURREY[0], SURREY[1], (SURREY[0] + SURREY[2]) / 2, SURREY[3])
    half, _ = synthetic_raster(west, 450, 400, seed=11)
    np.testing.assert_allclose(whole[:, :450], half, atol=1e-6)


def _stats_by_cell(data, transform, bounds, res=8, nodata=None):
    return {s.h3: s for s in aggregate_array(
        data, transform, bounds, dataset_id="d", t="2024-01", res=res,
        nodata=nodata)}


def test_merging_two_tiles_equals_aggregating_the_whole_raster():
    """The core claim. Split an extent, aggregate each half, merge the halves,
    and every cell must match what one pass over the whole thing produced —
    mean, min, max, standard deviation and valid fraction alike."""
    bounds = (-1.60, 52.45, -1.40, 52.55)
    mid = (bounds[0] + bounds[2]) / 2
    left = (bounds[0], bounds[1], mid, bounds[3])
    right = (mid, bounds[1], bounds[2], bounds[3])

    whole, tw = synthetic_raster(bounds, 512, 256, seed=5, lo=-0.2, hi=0.9)
    lo_data, tl = synthetic_raster(left, 256, 256, seed=5, lo=-0.2, hi=0.9)
    hi_data, tr = synthetic_raster(right, 256, 256, seed=5, lo=-0.2, hi=0.9)

    single = _stats_by_cell(whole, tw, bounds)
    a = _stats_by_cell(lo_data, tl, left)
    b = _stats_by_cell(hi_data, tr, right)

    merged = dict(a)
    for cell, stat in b.items():
        merged[cell] = merge_stats(merged[cell], stat) if cell in merged else stat

    shared = set(single) & set(merged)
    assert len(shared) > 20, "not enough overlap to be a real test"
    seam = 0
    for cell in shared:
        one, two = single[cell], merged[cell]
        assert two.n_valid == one.n_valid, f"pixel count differs for {cell}"
        assert two.mean == pytest.approx(one.mean, rel=1e-6)
        assert two.min == pytest.approx(one.min, rel=1e-6)
        assert two.max == pytest.approx(one.max, rel=1e-6)
        assert two.stddev == pytest.approx(one.stddev, rel=1e-6)
        assert two.valid_fraction == pytest.approx(one.valid_fraction, rel=1e-6)
        if cell in a and cell in b:
            seam += 1
    assert seam > 0, "no cell straddled the seam, so nothing was merged"


def test_merging_is_exact_for_cells_that_straddle_a_seam_unevenly():
    """The case a naive average-of-averages gets wrong: 90% of a cell in one
    tile and 10% in the other must not weight the two halves equally."""
    big = CellStat(1, "d", "t", mean=10.0, min=10.0, max=10.0, stddev=0.0,
                   valid_fraction=1.0, n_valid=900, n_total=900, m2=0.0)
    small = CellStat(1, "d", "t", mean=20.0, min=20.0, max=20.0, stddev=0.0,
                     valid_fraction=1.0, n_valid=100, n_total=100, m2=0.0)
    merged = merge_stats(big, small)
    assert merged.mean == pytest.approx(11.0)        # not 15.0
    assert merged.n_valid == 1000
    assert merged.min == 10.0 and merged.max == 20.0
    assert merged.stddev == pytest.approx(3.0)       # sqrt(0.9*1 + 0.1*81)


def test_merging_an_empty_sliver_only_moves_the_denominator():
    """A tile edge clipping the corner of a cloud-covered cell contributes
    pixels to the total but nothing to the mean."""
    real = CellStat(1, "d", "t", 0.5, 0.4, 0.6, 0.1, 1.0,
                    n_valid=100, n_total=100, m2=1.0)
    empty = CellStat(1, "d", "t", None, None, None, None, 0.0,
                     n_valid=0, n_total=25, m2=0.0)
    merged = merge_stats(real, empty)
    assert merged.mean == pytest.approx(0.5)
    assert merged.n_valid == 100 and merged.n_total == 125
    assert merged.valid_fraction == pytest.approx(0.8)


def test_merging_two_empty_slivers_stays_empty():
    empty = CellStat(1, "d", "t", None, None, None, None, 0.0,
                     n_valid=0, n_total=10, m2=0.0)
    merged = merge_stats(empty, empty)
    assert merged.mean is None and merged.n_valid == 0
    assert merged.n_total == 20 and merged.valid_fraction == 0.0


def test_merging_categorical_cells_adds_the_histograms():
    a = CellStat(1, "d", "t", None, None, None, None, 1.0,
                 class_counts={10: 5, 20: 3}, n_valid=8, n_total=8)
    b = CellStat(1, "d", "t", None, None, None, None, 1.0,
                 class_counts={20: 2, 30: 1}, n_valid=3, n_total=3)
    merged = merge_stats(a, b)
    assert merged.class_counts == {10: 5, 20: 5, 30: 1}
    assert merged.mean is None, "class codes must never be averaged"


def test_merging_refuses_statistics_from_different_cells():
    a = CellStat(1, "d", "t", 1.0, 1.0, 1.0, 0.0, 1.0, n_valid=1, n_total=1)
    b = CellStat(2, "d", "t", 1.0, 1.0, 1.0, 0.0, 1.0, n_valid=1, n_total=1)
    with pytest.raises(ValueError):
        merge_stats(a, b)


# --------------------------------------------------------------------------
# The resume
# --------------------------------------------------------------------------
def test_progress_is_keyed_by_tile_not_by_timestep(tmp_path):
    """The whole point of the migration. One tile finishing must not mark the
    timestep done."""
    p = FileProgress(tmp_path / "p.json")
    p.mark("ndvi", "2024-01", "r00c00", 8, 120, "4x3")
    assert p.done("ndvi", "2024-01", "r00c00", 8)
    assert not p.done("ndvi", "2024-01", "r00c01", 8)
    assert not p.done("ndvi", "2024-01", "r00c00", 7), "tiers are tracked apart"
    assert not p.done("ndvi", "2024-02", "r00c00", 8)


def test_progress_survives_the_process_that_wrote_it(tmp_path):
    path = tmp_path / "p.json"
    first = FileProgress(path)
    first.mark("ndvi", "2024-01", "r00c00", 8, 120, "4x3")
    assert FileProgress(path).done("ndvi", "2024-01", "r00c00", 8)


def test_progress_records_the_grid_so_a_changed_tiling_is_detectable(tmp_path):
    p = FileProgress(tmp_path / "p.json")
    assert p.grid_for("ndvi") is None
    p.mark("ndvi", "2024-01", "r00c00", 8, 120, "4x3")
    assert p.grid_for("ndvi") == "4x3"


def test_a_corrupt_progress_file_costs_work_not_the_run(tmp_path):
    """Every stage is idempotent, so redoing work is survivable and refusing
    to start is not."""
    path = tmp_path / "p.json"
    path.write_text("{not json at all")
    p = FileProgress(path)
    assert not p.done("ndvi", "2024-01", "r00c00", 8)
    p.mark("ndvi", "2024-01", "r00c00", 8, 1, "1x1")
    assert json.loads(path.read_text())


# --------------------------------------------------------------------------
# End to end through the runner
# --------------------------------------------------------------------------
def _surrey_manifest(tmp_path, steps=2):
    from ingest.manifest import Manifest

    return Manifest.from_dict({
        "id": "tile_test", "kind": "continuous", "unit": "index",
        "nodata": -9999,
        "source": {"driver": "earthengine"},
        "temporal": {"step": "monthly", "start": "2024-01",
                     "end": f"2024-{steps:02d}"},
        "spatial": {"resolution_m": 300, "bbox": list(SURREY)},
        "h3_resolutions": [8],
    })


def test_a_tiled_run_writes_one_cog_per_tile_per_timestep(tmp_path):
    pytest.importorskip("rasterio")
    from ingest.run import run_manifest

    m = _surrey_manifest(tmp_path)
    stats = {}
    run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path, dsn=None,
                 dry_run=False, tile_pixels=5_000, stats_out=stats)

    assert stats["tiles"] > 1, "the budget should have forced a grid"
    written = sorted(p.name for p in (tmp_path / "tile_test" / "2024" / "01").glob("*.tif"))
    assert len(written) == stats["tiles"]
    assert written[0].startswith("r00c00")


def test_an_interrupted_run_resumes_from_the_tile_it_reached(tmp_path):
    """The requirement in one test. Kill a run partway, start it again, and it
    must do the remaining tiles and only those."""
    pytest.importorskip("rasterio")
    from ingest import run as run_mod

    m = _surrey_manifest(tmp_path, steps=2)

    # Fail on the fourth tile, the way a killed process or a dropped
    # connection would — after some work is committed, not before any.
    real_fetch = run_mod.fetch_raster
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 4:
            raise RuntimeError("worker died")
        return real_fetch(*args, **kwargs)

    run_mod.fetch_raster = flaky
    try:
        with pytest.raises(RuntimeError):
            run_mod.run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path,
                                 dsn=None, dry_run=False, tile_pixels=5_000)
        done_before = calls["n"] - 1
    finally:
        run_mod.fetch_raster = real_fetch

    stats = {}
    run_mod.run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path,
                         dsn=None, dry_run=False, tile_pixels=5_000,
                         stats_out=stats)

    total = stats["tiles"] * 2                       # two timesteps
    assert stats["skipped"] == done_before, (
        "the resumed run must skip exactly the tiles that completed")
    assert stats["steps"] == total - done_before, (
        "and do exactly the ones that did not")

    # A third run has nothing left to do at all.
    again = {}
    run_mod.run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path,
                         dsn=None, dry_run=False, tile_pixels=5_000,
                         stats_out=again)
    assert again["steps"] == 0 and again["skipped"] == total


def test_restart_ignores_progress_and_redoes_everything(tmp_path):
    pytest.importorskip("rasterio")
    from ingest.run import run_manifest

    m = _surrey_manifest(tmp_path, steps=1)
    first, second = {}, {}
    run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path, dsn=None,
                 dry_run=False, tile_pixels=5_000, stats_out=first)
    run_manifest(m, synthetic=True, limit=None, out_dir=tmp_path, dsn=None,
                 dry_run=False, tile_pixels=5_000, restart=True, stats_out=second)
    assert second["steps"] == first["steps"] and second["skipped"] == 0
