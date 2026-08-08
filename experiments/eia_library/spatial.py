"""Does the geometry re-identify the site, even after the text is clean?

This is the test that matters more, and it is the one the context doc does not
mention. Item 11 wants a library of environmental assessments that is useful
*because it is spatial* — findings you can look up for a place. But for a
development site, the location is not metadata attached to the record. It very
nearly is the record's identity: a site boundary is drawn from a title plan or
a red-line application, both of which are public, and matching a polygon back
to the application it came from is a spatial join, not an attack.

So a "de-identified" EIA that keeps its boundary is not de-identified. The two
things the feature wants — precise spatial lookup, and anonymity — are in
direct tension, and the question is what is left when you resolve it.

Two measurements:

1. **Does coordinate fuzzing help?** Round a boundary progressively and see
   whether it stays uniquely matchable to its original among its neighbours.
2. **What does generalising to a cell cost?** If fuzzing does not work, the
   only remaining option is to drop the boundary and keep a cell — so how
   coarse must the cell be, and is the finding still worth anything there.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, NamedTuple, Tuple

import h3

Ring = List[Tuple[float, float]]


# ---------------------------------------------------------------------------
# A synthetic population of development sites
# ---------------------------------------------------------------------------
def make_sites(n: int = 400, seed: int = 7) -> List[Ring]:
    """Irregular parcels of a realistic size, scattered across Surrey.

    Deliberately not rectangles. A real red-line boundary follows hedges and
    ownership, and it is that irregularity which makes it a fingerprint — a
    plain rectangle would understate the problem and flatter the result.
    """
    rng = random.Random(seed)
    sites: List[Ring] = []
    for _ in range(n):
        clng = rng.uniform(-0.75, -0.35)
        clat = rng.uniform(51.15, 51.35)
        # 0.4–6 ha, the range a village-edge application actually covers.
        # Radius of the equivalent circle, in degrees of latitude.
        target_ha = rng.uniform(0.4, 6.0)
        radius_deg = math.sqrt(target_ha * 10_000 / math.pi) / 111_320
        vertices = rng.randint(6, 14)
        ring: Ring = []
        for i in range(vertices):
            a = (i / vertices) * math.tau
            r = radius_deg * rng.uniform(0.55, 1.45)
            ring.append((clng + r * math.cos(a) / math.cos(math.radians(clat)),
                         clat + r * math.sin(a)))
        ring.append(ring[0])
        sites.append(ring)
    return sites


# ---------------------------------------------------------------------------
# Shape descriptors — what an attacker matches on
# ---------------------------------------------------------------------------
def area_ha(ring: Ring) -> float:
    """Shoelace on a local equirectangular projection. Good to a fraction of a
    percent over a few hundred metres, which is all this needs."""
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    acc = 0.0
    for i in range(len(ring) - 1):
        x1, y1 = ring[i][0] * k, ring[i][1]
        x2, y2 = ring[i + 1][0] * k, ring[i + 1][1]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2 * (111_320 ** 2) / 10_000


def perimeter_m(ring: Ring) -> float:
    lat0 = sum(p[1] for p in ring) / len(ring)
    k = math.cos(math.radians(lat0))
    return sum(
        math.hypot((ring[i + 1][0] - ring[i][0]) * k,
                   ring[i + 1][1] - ring[i][1]) * 111_320
        for i in range(len(ring) - 1)
    )


def descriptor(ring: Ring) -> Tuple[float, float, int]:
    """What survives every transformation short of deletion: how big it is,
    how crinkly it is, and how many corners it has. No absolute position."""
    return (area_ha(ring), perimeter_m(ring), len(ring) - 1)


def round_ring(ring: Ring, places: int) -> Ring:
    return [(round(x, places), round(y, places)) for x, y in ring]


# ---------------------------------------------------------------------------
# Test 1 — does fuzzing the coordinates help?
# ---------------------------------------------------------------------------
class FuzzResult(NamedTuple):
    places: int
    metres: float
    uniquely_matched: float


def _match_rate(sites: List[Ring], places: int) -> float:
    """Fraction of fuzzed sites that match their own original, and only their
    own, among the whole population.

    The attacker's method is the obvious one: compute the same descriptor on
    the published shape, compute it on every candidate boundary from the
    planning register, and take the nearest. No cleverness required.
    """
    originals = [descriptor(r) for r in sites]
    hits = 0
    for i, ring in enumerate(sites):
        d = descriptor(round_ring(ring, places))
        best, best_j = None, -1
        for j, o in enumerate(originals):
            # Scale each component so none dominates: hectares are order 1,
            # metres order 100s.
            dist = ((d[0] - o[0]) / 0.05) ** 2 + ((d[1] - o[1]) / 5.0) ** 2 \
                + ((d[2] - o[2]) * 10) ** 2
            if best is None or dist < best:
                best, best_j = dist, j
        if best_j == i:
            hits += 1
    return hits / len(sites)


def fuzz_table(sites: List[Ring]) -> List[FuzzResult]:
    out = []
    for places in (5, 4, 3, 2):
        # Degrees of latitude to metres, at England's latitude.
        metres = 10 ** (-places) * 111_320
        out.append(FuzzResult(places, metres, _match_rate(sites, places)))
    return out


# ---------------------------------------------------------------------------
# Test 2 — what does generalising to a cell cost?
# ---------------------------------------------------------------------------
class CellResult(NamedTuple):
    resolution: int
    edge_m: float
    area_ha: float
    sites_per_cell: float
    density_for_k5: float
    verdict: str


def cell_table(sites: List[Ring]) -> List[CellResult]:
    """How many of our synthetic sites land in the same H3 cell, by resolution.

    `sites_per_cell` is the crowd a site hides in. One means it does not hide
    at all: publishing the cell publishes the site.
    """
    out = []
    for res in (10, 9, 8, 7, 6, 5):
        cells: Dict[str, int] = {}
        for ring in sites:
            lng = sum(p[0] for p in ring[:-1]) / (len(ring) - 1)
            lat = sum(p[1] for p in ring[:-1]) / (len(ring) - 1)
            c = h3.latlng_to_cell(lat, lng, res)
            cells[c] = cells.get(c, 0) + 1
        occupied = [v for v in cells.values()]
        mean = sum(occupied) / len(occupied)
        km2 = h3.average_hexagon_area(res, unit="km^2")
        area = km2 * 100  # ha
        edge = h3.average_hexagon_edge_length(res, unit="m")
        # The density-free version of the same question. `sites_per_cell`
        # above depends on the synthetic population being the right density;
        # this does not. k=5 is the usual floor for a released aggregate — the
        # ONS threshold for a census cell is the same order.
        density_for_k5 = 5 / km2
        verdict = "identifies the site" if mean < 2 else (
            "thin cover" if mean < 5 else "plausible crowd")
        out.append(CellResult(res, edge, area, mean, density_for_k5, verdict))
    return out


def report() -> str:
    sites = make_sites()
    lines = ["", "TEST B — does the geometry give the site away?", ""]
    lines.append(f"  population: {len(sites)} synthetic sites, "
                 f"{min(area_ha(s) for s in sites):.1f}–"
                 f"{max(area_ha(s) for s in sites):.1f} ha, across ~30 x 22 km")
    lines.append("")
    lines.append("  1. Fuzzing the coordinates")
    lines.append("     decimals   precision   still matched to its own original")
    for r in fuzz_table(sites):
        lines.append(f"     {r.places:>5}      {r.metres:>7.0f} m   "
                     f"{r.uniquely_matched:>6.1%}")
    lines.append("")
    lines.append("  2. Generalising to an H3 cell")
    lines.append("     res    edge      cell area   sites/cell  "
                 "sites/km2 needed for k=5")
    for c in cell_table(sites):
        lines.append(f"     {c.resolution:>3}  {c.edge_m:>7.0f} m  "
                     f"{c.area_ha:>10.1f} ha  {c.sites_per_cell:>8.2f}  "
                     f"{c.density_for_k5:>13.2f}   {c.verdict}")
    lines.append("")
    lines.append("     The last column is the one that does not depend on the")
    lines.append("     synthetic population: it is how thickly EIA'd sites would")
    lines.append("     have to be spread on the ground for a cell of that size to")
    lines.append("     hide one among five.")
    return "\n".join(lines)
