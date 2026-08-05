"""
The parts of tiling that only a real database can prove.

Two things live in SQL and cannot be checked anywhere else: the migration that
adds the tile column to an existing table, and the UPSERT that merges a tile's
statistics into rows another tile already wrote. The merge is Chan's parallel
variance algorithm written twice — once in Python in `aggregate.merge_stats`,
once in SQL in `run._load` — and two copies of an algorithm is exactly the
situation where they drift apart silently.

Skipped without a server. Set `INGEST_TEST_DSN` to run them:

    pg_ctlcluster 16 main start
    createdb ingest_test
    INGEST_TEST_DSN=postgresql://postgres@127.0.0.1/ingest_test python -m pytest tests/test_ingest_postgres.py
"""

import os
import uuid

import pytest

from ingest.aggregate import CellStat, merge_stats

DSN = os.environ.get("INGEST_TEST_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="INGEST_TEST_DSN is not set")


@pytest.fixture
def conn():
    psycopg = pytest.importorskip("psycopg")
    from ingest import migrate

    with psycopg.connect(DSN, autocommit=False) as c:
        migrate.apply(c, (8,), verbose=False)
        yield c
        c.rollback()


def _stat(dataset, cell, **kw):
    base = dict(mean=None, min=None, max=None, stddev=None, valid_fraction=0.0,
                n_valid=0, n_total=0, m2=0.0)
    base.update(kw)
    return CellStat(h3=cell, dataset_id=dataset, t="2024-01", **base)


def _load_and_read(conn, dataset, stats):
    from ingest.run import _load

    for stat in stats:
        _load(conn, 8, [stat])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT mean, min, max, stddev, valid_fraction, n_valid, n_total, m2 "
            "FROM cell_stats_r8 WHERE dataset_id = %s", (dataset,))
        return cur.fetchone()


# --------------------------------------------------------------------------
# The migration
# --------------------------------------------------------------------------
def test_the_migration_is_idempotent(conn):
    """It runs at the start of every ingest, so running it twice must be a
    no-op rather than an error."""
    from ingest import migrate

    assert migrate.apply(conn, (8,), verbose=False) == 0


def test_progress_is_keyed_by_tile_in_the_database(conn):
    """The column the migration exists for. Two tiles of one timestep must be
    two rows, not one overwriting the other."""
    dataset = f"t{uuid.uuid4().hex[:8]}"
    with conn.cursor() as cur:
        for tile in ("r00c00", "r00c01"):
            cur.execute(
                "INSERT INTO ingest_progress (dataset_id, t, h3_res, tile, grid, n_cells)"
                " VALUES (%s, '2024-01', 8, %s, '2x1', 10)", (dataset, tile))
        cur.execute("SELECT count(*) FROM ingest_progress WHERE dataset_id = %s",
                    (dataset,))
        assert cur.fetchone()[0] == 2


def test_legacy_progress_rows_survive_as_the_untiled_tile(conn):
    """Rows written before tiling existed carry tile '-', so a pre-tiling
    dataset is still seen as done and is not silently re-ingested."""
    with conn.cursor() as cur:
        cur.execute("SELECT column_default FROM information_schema.columns "
                    "WHERE table_name = 'ingest_progress' AND column_name = 'tile'")
        assert "'-'" in cur.fetchone()[0]


# --------------------------------------------------------------------------
# The merge
# --------------------------------------------------------------------------
@pytest.mark.parametrize("a_kw, b_kw", [
    # Even halves.
    (dict(mean=0.4, min=0.1, max=0.7, stddev=0.2, valid_fraction=1.0,
          n_valid=100, n_total=100, m2=4.0),
     dict(mean=0.6, min=0.3, max=0.9, stddev=0.1, valid_fraction=1.0,
          n_valid=100, n_total=100, m2=1.0)),
    # Badly uneven — the case an average of averages gets wrong.
    (dict(mean=10.0, min=10.0, max=10.0, stddev=0.0, valid_fraction=1.0,
          n_valid=900, n_total=900, m2=0.0),
     dict(mean=20.0, min=20.0, max=20.0, stddev=0.0, valid_fraction=1.0,
          n_valid=100, n_total=100, m2=0.0)),
    # A sliver with no usable pixels: denominator only.
    (dict(mean=0.5, min=0.4, max=0.6, stddev=0.1, valid_fraction=1.0,
          n_valid=100, n_total=100, m2=1.0),
     dict(n_valid=0, n_total=25)),
    # The empty side arriving first.
    (dict(n_valid=0, n_total=25),
     dict(mean=0.5, min=0.4, max=0.6, stddev=0.1, valid_fraction=1.0,
          n_valid=100, n_total=100, m2=1.0)),
])
def test_the_sql_merge_matches_the_python_merge(conn, a_kw, b_kw):
    """Two implementations of one algorithm. If they disagree, the fast tier
    and every test that checks it are describing different databases."""
    dataset = f"t{uuid.uuid4().hex[:8]}"
    a, b = _stat(dataset, 1, **a_kw), _stat(dataset, 1, **b_kw)

    row = _load_and_read(conn, dataset, [a, b])
    expected = merge_stats(a, b)

    mean, lo, hi, stddev, valid_fraction, n_valid, n_total, m2 = row
    assert n_valid == expected.n_valid
    assert n_total == expected.n_total
    assert valid_fraction == pytest.approx(expected.valid_fraction, rel=1e-5)
    if expected.mean is None:
        assert mean is None
    else:
        assert mean == pytest.approx(expected.mean, rel=1e-5)
        assert lo == pytest.approx(expected.min, rel=1e-5)
        assert hi == pytest.approx(expected.max, rel=1e-5)
        assert stddev == pytest.approx(expected.stddev, rel=1e-4)
        assert m2 == pytest.approx(expected.m2, rel=1e-4)


def test_the_merge_is_order_independent(conn):
    """Tiles complete in whatever order the scheduler runs them. The answer
    must not depend on which one arrived first."""
    one, two = f"t{uuid.uuid4().hex[:8]}", f"t{uuid.uuid4().hex[:8]}"
    kw_a = dict(mean=0.4, min=0.1, max=0.7, stddev=0.2, valid_fraction=1.0,
                n_valid=300, n_total=300, m2=12.0)
    kw_b = dict(mean=0.9, min=0.8, max=1.0, stddev=0.05, valid_fraction=1.0,
                n_valid=50, n_total=60, m2=0.125)

    forward = _load_and_read(conn, one, [_stat(one, 1, **kw_a), _stat(one, 1, **kw_b)])
    backward = _load_and_read(conn, two, [_stat(two, 1, **kw_b), _stat(two, 1, **kw_a)])
    for x, y in zip(forward, backward):
        assert x == pytest.approx(y, rel=1e-5)


def test_three_tiles_merge_as_one_pass(conn):
    """A cell can touch more than two tiles — a grid corner touches four. The
    merge has to stay exact however many arrive."""
    dataset = f"t{uuid.uuid4().hex[:8]}"
    parts = [
        _stat(dataset, 1, mean=1.0, min=1.0, max=1.0, stddev=0.0,
              valid_fraction=1.0, n_valid=10, n_total=10, m2=0.0),
        _stat(dataset, 1, mean=2.0, min=2.0, max=2.0, stddev=0.0,
              valid_fraction=1.0, n_valid=20, n_total=20, m2=0.0),
        _stat(dataset, 1, mean=3.0, min=3.0, max=3.0, stddev=0.0,
              valid_fraction=1.0, n_valid=30, n_total=30, m2=0.0),
    ]
    row = _load_and_read(conn, dataset, parts)
    expected = merge_stats(merge_stats(parts[0], parts[1]), parts[2])

    assert row[0] == pytest.approx(expected.mean, rel=1e-5)   # (10+40+90)/60
    assert row[5] == 60
    assert row[3] == pytest.approx(expected.stddev, rel=1e-4)


def test_a_tiled_run_and_an_untiled_run_reach_the_same_table(conn):
    """The end-to-end claim, through the real runner and the real database:
    ingesting an extent in one pass and in nine tiles must produce the same
    fast tier, cell for cell."""
    pytest.importorskip("rasterio")
    import tempfile

    from ingest.manifest import Manifest
    from ingest.run import run_manifest

    def ingest(dataset_id, tile_pixels):
        m = Manifest.from_dict({
            "id": dataset_id, "kind": "continuous", "unit": "index",
            # The same synthetic surface for both runs: different dataset ids
            # so they can sit in the table together, identical pixels so they
            # can be compared at all.
            "nodata": -9999,
            "source": {"driver": "earthengine", "seed": "tiling-equivalence"},
            "temporal": {"step": "monthly", "start": "2024-01", "end": "2024-01"},
            "spatial": {"resolution_m": 200, "bbox": [-0.85, 51.07, 0.06, 51.47]},
            "h3_resolutions": [8],
        })
        with tempfile.TemporaryDirectory() as out:
            run_manifest(m, synthetic=True, limit=None, out_dir=__import__(
                "pathlib").Path(out), dsn=DSN, dry_run=False,
                tile_pixels=tile_pixels)

    whole = f"t{uuid.uuid4().hex[:8]}"
    split = f"t{uuid.uuid4().hex[:8]}"
    ingest(whole, 50_000_000)          # one pass
    ingest(split, 20_000)              # forced into a grid

    with conn.cursor() as cur:
        cur.execute(
            "SELECT h3, mean, min, max, stddev, n_valid, n_total "
            "FROM cell_stats_r8 WHERE dataset_id = ANY(%s) ORDER BY dataset_id, h3",
            ([whole, split],))
        rows = cur.fetchall()

    by_cell = {}
    for h3_id, *values in rows:
        by_cell.setdefault(h3_id, []).append(values)

    compared = 0
    for h3_id, pair in by_cell.items():
        if len(pair) != 2:
            continue
        one, two = pair
        assert two[4] == one[4], f"pixel counts differ for cell {h3_id}"
        for i, name in enumerate(("mean", "min", "max", "stddev")):
            if one[i] is None:
                assert two[i] is None
            else:
                assert two[i] == pytest.approx(one[i], rel=1e-4), \
                    f"{name} differs for cell {h3_id}"
        compared += 1
    assert compared > 50, "not enough cells in common to be a real comparison"
