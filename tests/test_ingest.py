"""Tests for the ingest pipeline.

Everything here runs offline against synthetic rasters — no cloud, no
credentials, no network. That is deliberate: the pipeline was built this way so
that cloud day is spent pointing it at real data rather than writing it.
"""

import numpy as np
import pytest

from ingest.aggregate import aggregate_array, cells_for_bounds
from ingest.cog import synthetic_raster, write_cog
from ingest.manifest import Manifest

BOUNDS = (-1.60, 52.45, -1.40, 52.55)     # a small window near Coventry


def _raster(**kw):
    return synthetic_raster(BOUNDS, 256, 256, seed=7, **kw)


# --------------------------------------------------------------------------
# Manifests
# --------------------------------------------------------------------------
def test_monthly_manifest_expands_to_every_step():
    m = Manifest.from_dict({
        "id": "x", "kind": "continuous", "unit": "index",
        "source": {"driver": "earthengine"},
        "temporal": {"step": "monthly", "start": "2011-01", "end": "2025-12"},
        "spatial": {"resolution_m": 10},
    })
    steps = m.timesteps()
    assert len(steps) == 180
    assert steps[0] == "2011-01" and steps[-1] == "2025-12"


def test_annual_manifest_steps_by_year():
    m = Manifest.from_dict({
        "id": "x", "kind": "continuous", "unit": "%",
        "source": {}, "temporal": {"step": "annual", "start": "2011-01", "end": "2025-01"},
        "spatial": {"resolution_m": 10},
    })
    assert len(m.timesteps()) == 15


def test_static_manifest_has_one_step():
    m = Manifest.from_dict({
        "id": "x", "kind": "continuous", "unit": "m",
        "source": {}, "temporal": {"step": "static"},
        "spatial": {"resolution_m": 2},
    })
    assert m.timesteps() == ["static"]
    assert m.asset_key("static") == "x/static.tif"


def test_manifest_rejects_a_temporal_step_with_no_range():
    with pytest.raises(ValueError, match="requires start and end"):
        Manifest.from_dict({
            "id": "x", "kind": "continuous", "unit": "m",
            "source": {}, "temporal": {"step": "monthly"},
            "spatial": {"resolution_m": 10},
        })


def test_manifest_rejects_an_unknown_kind():
    with pytest.raises(ValueError, match="continuous/categorical"):
        Manifest.from_dict({
            "id": "x", "kind": "ordinal", "unit": "m",
            "source": {}, "temporal": {"step": "static"},
            "spatial": {"resolution_m": 10},
        })


def test_shipped_manifests_all_parse():
    from pathlib import Path
    paths = sorted(Path("ingest/manifests").glob("*.yaml"))
    assert paths, "no manifests found"
    for p in paths:
        m = Manifest.load(p)
        assert m.timesteps()


# --------------------------------------------------------------------------
# Cell selection — the finding from BENCHMARK.md
# --------------------------------------------------------------------------
def test_cells_cover_the_bounds_at_both_tiers():
    for res in (7, 8):
        cells = cells_for_bounds(BOUNDS, res)
        assert cells, f"res {res} produced no cells"
    # A finer tier must produce strictly more cells for the same area.
    assert len(cells_for_bounds(BOUNDS, 8)) > len(cells_for_bounds(BOUNDS, 7))


def test_a_box_smaller_than_one_cell_still_selects_cells():
    """The bug BENCHMARK.md caught. Default H3 containment keeps only cells
    whose centre is inside the polygon, so a 20 ha field returned nothing at
    all. Overlap containment must never return an empty set for a real area."""
    tiny = (-1.5000, 52.5000, -1.4995, 52.4997)      # roughly 2 ha
    assert cells_for_bounds(tiny, 8)


# --------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------
def test_aggregate_produces_stats_within_the_source_range():
    data, transform = _raster(lo=-0.2, hi=0.9)
    stats = list(aggregate_array(data, transform, BOUNDS,
                                 dataset_id="t", t="2020-01", res=8))
    assert stats
    for s in stats:
        if s.mean is None:
            continue
        assert -0.2 <= s.min <= s.mean <= s.max <= 0.9
        assert s.stddev >= 0
        assert 0.0 <= s.valid_fraction <= 1.0


def test_valid_fraction_tracks_the_nodata_holes():
    """15% nodata in must read as roughly 85% valid out. If this drifts, every
    confidence indicator in the UI is lying."""
    data, transform = _raster(nodata=-9999.0, nodata_fraction=0.15)
    stats = [s for s in aggregate_array(data, transform, BOUNDS, dataset_id="t",
                                        t="2020-01", res=8, nodata=-9999.0)
             if s.mean is not None]
    assert stats
    mean_valid = sum(s.valid_fraction for s in stats) / len(stats)
    assert 0.80 < mean_valid < 0.90


def test_nodata_never_leaks_into_the_statistics():
    data, transform = _raster(lo=0.0, hi=1.0, nodata=-9999.0, nodata_fraction=0.3)
    for s in aggregate_array(data, transform, BOUNDS, dataset_id="t",
                             t="2020-01", res=8, nodata=-9999.0):
        if s.min is not None:
            assert s.min >= 0.0, "sentinel value reached the statistics"


def test_categorical_aggregation_counts_classes_and_never_averages():
    """The mean of two land-cover codes is meaningless — a categorical raster
    must produce a histogram and no mean at all."""
    data, transform = _raster(kind="categorical")
    stats = list(aggregate_array(data, transform, BOUNDS, dataset_id="lc",
                                 t="2020", res=8, kind="categorical"))
    assert stats
    for s in stats:
        assert s.mean is None and s.min is None and s.max is None
        if s.class_counts:
            assert all(isinstance(k, int) for k in s.class_counts)
            assert sum(s.class_counts.values()) > 0


def test_the_two_tiers_agree_on_the_overall_mean():
    """A coarse tier aggregates the same pixels into fewer cells, so the
    area-weighted mean should barely move. A large gap means the pixel
    indexing is wrong at one resolution."""
    data, transform = _raster(lo=0.0, hi=1.0)
    means = {}
    for res in (7, 8):
        stats = [s for s in aggregate_array(data, transform, BOUNDS,
                                            dataset_id="t", t="2020-01", res=res)
                 if s.mean is not None]
        means[res] = sum(s.mean for s in stats) / len(stats)
    assert abs(means[7] - means[8]) < 0.05


def test_cells_with_no_usable_pixels_are_recorded_not_dropped():
    """A blank cell is a fact the UI needs — it is how a gap is distinguished
    from a cell nobody asked about."""
    data, transform = _raster(nodata=-9999.0)
    data[:] = -9999.0
    stats = list(aggregate_array(data, transform, BOUNDS, dataset_id="t",
                                 t="2020-01", res=8, nodata=-9999.0))
    assert stats
    assert all(s.mean is None and s.valid_fraction == 0.0 for s in stats)


def test_aggregate_is_deterministic():
    data, transform = _raster()
    a = list(aggregate_array(data, transform, BOUNDS, dataset_id="t", t="x", res=8))
    b = list(aggregate_array(data, transform, BOUNDS, dataset_id="t", t="x", res=8))
    assert [s.as_row() for s in a] == [s.as_row() for s in b]


# --------------------------------------------------------------------------
# COG writing
# --------------------------------------------------------------------------
def test_written_cog_is_tiled_and_has_overviews(tmp_path):
    """Both properties are what make range reads work. A plain untiled GeoTIFF
    on object storage has to be fetched whole, which defeats the entire
    'nothing is downloaded' premise."""
    rasterio = pytest.importorskip("rasterio")
    data, transform = _raster()
    path = write_cog(tmp_path / "t.tif", data, transform, "EPSG:4326")
    with rasterio.open(path) as src:
        assert src.profile["tiled"] is True
        assert src.profile["blockxsize"] == 512
        assert src.overviews(1), "no overviews built"
        assert src.compression is not None


def test_cog_roundtrips_its_values(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    data, transform = _raster(lo=0.0, hi=1.0)
    path = write_cog(tmp_path / "t.tif", data, transform, "EPSG:4326")
    with rasterio.open(path) as src:
        np.testing.assert_allclose(src.read(1), data, rtol=1e-5)


# --------------------------------------------------------------------------
# The runner's extent handling
#
# These exist because `--synthetic` used to generate a fixed 512x512 tile over
# a hard-coded window regardless of the manifest, which made every timing taken
# from it meaningless — see docs/INGEST-BENCHMARK.md, "Two bugs this run
# found". A regression here would be silent and would only show up as a
# benchmark that measures nothing.
# --------------------------------------------------------------------------
def test_raster_shape_accounts_for_longitude_shrinking_with_latitude():
    """One degree of longitude is ~62% of a degree of latitude in metres at
    England's latitude, so a degree-square window is 62% as wide in pixels as
    it is tall. Using one pixel size for both stretches the raster by 60% and
    quietly corrupts every cell statistic."""
    import math

    from ingest.run import raster_shape

    w, h = raster_shape((-0.5, 51.07, 0.5, 52.07), 10)
    assert h == pytest.approx(1.0 * 111_320 / 10, rel=0.01)
    assert w / h == pytest.approx(math.cos(math.radians(51.57)), rel=0.01)


def test_raster_shape_scales_with_resolution():
    from ingest.run import raster_shape

    coarse = raster_shape((-0.85, 51.07, 0.06, 51.47), 100)
    fine = raster_shape((-0.85, 51.07, 0.06, 51.47), 10)
    assert fine[0] == pytest.approx(coarse[0] * 10, rel=0.01)
    assert fine[1] == pytest.approx(coarse[1] * 10, rel=0.01)


def test_the_surrey_manifest_is_the_extent_the_benchmark_measured():
    """docs/INGEST-BENCHMARK.md quotes 6,338 x 4,453 px. If the manifest moves,
    every number in that document silently stops applying to it."""
    from ingest.run import raster_shape

    m = Manifest.load("ingest/manifests/ndvi_s2_surrey.yaml")
    assert raster_shape(m.spatial.bbox, m.spatial.resolution_m) == (6338, 4453)


def test_a_national_raster_at_ten_metres_is_refused_rather_than_attempted():
    """4.2 billion pixels is 16.7 GB before the COG writer takes its copy. The
    OOM reaper arriving at month nine of a backfill is a much worse failure
    than an error message at month one."""
    from ingest.run import fetch_raster

    m = Manifest.load("ingest/manifests/ndvi_s2.yaml")     # England, 10 m
    with pytest.raises(SystemExit) as exc:
        fetch_raster(m, "2024-01", synthetic=True, out_dir=None)
    assert "will not fit in memory" in str(exc.value)
    assert "--window" in str(exc.value), "the error must say what to do instead"


def test_a_synthetic_raster_covers_the_window_it_was_asked_for():
    from ingest.run import fetch_raster

    m = Manifest.load("ingest/manifests/ndvi_s2.yaml")
    window = (-0.85, 51.07, -0.80, 51.10)
    data, transform, bounds = fetch_raster(m, "2024-01", synthetic=True,
                                           out_dir=None, window=window)
    assert bounds == window
    # Corners of the array map back to the corners of the window.
    west, north = transform * (0, 0)
    east, south = transform * (data.shape[1], data.shape[0])
    assert (west, south, east, north) == pytest.approx(window, abs=1e-6)
