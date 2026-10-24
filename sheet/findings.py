"""
Turn layer results into plain findings.

A finding states what the published data shows and where — "Box Hill SSSI,
450 m NE". It never grades the site, scores it, or says whether a proposal
is acceptable. That judgement belongs to the ecologist reading the sheet.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from shapely.geometry.base import BaseGeometry

from .fetch import NONE_FOUND, NOT_ASSESSED, PRESENT, LayerResult
from .geometry import bearing_word
from .layers import GROUPS

ON_SITE_TOLERANCE_M = 0.5   # survey slop: touching the line counts as on site


@dataclass
class Item:
    label: str
    distance_m: float           # 0 = within or touching the red line
    direction: str
    count: int = 1              # polygons sharing this label

    def where(self) -> str:
        if self.distance_m <= ON_SITE_TOLERANCE_M:
            return "within the red line"
        d = self.distance_m
        dist = f"{d:,.0f} m" if d < 1000 else f"{d / 1000:.1f} km"
        return f"{dist} {self.direction}".strip()


@dataclass
class LayerFinding:
    layer_id: str
    name: str
    group: str
    status: str
    search_m: int
    items: List[Item] = field(default_factory=list)
    on_site: bool = False
    partial_coverage: bool = False
    note: str = ""
    error: str = ""

    def summary(self, max_items: int = 3) -> str:
        if self.status == NOT_ASSESSED:
            return "Not assessed — data could not be retrieved."
        radius = "the red line" if self.search_m == 0 else f"{self._radius()} of the red line"
        if self.status == NONE_FOUND:
            s = f"None found within {radius}."
            if self.partial_coverage:
                s += " Published data is incomplete for some councils — confirm locally."
            return s
        parts = []
        for it in self.items[:max_items]:
            name = it.label or "Unnamed area"
            if it.count > 1:
                name += f" ({it.count} parcels)"
            parts.append(f"{name}, {it.where()}")
        more = len(self.items) - max_items
        if more > 0:
            parts.append(f"+{more} more")
        return "; ".join(parts) + "."

    def _radius(self) -> str:
        m = self.search_m
        return f"{m:,} m" if m < 1000 else f"{m // 1000} km"


def _items(result: LayerResult, site: BaseGeometry) -> List[Item]:
    by_label: Dict[str, Item] = {}
    for f in result.features:
        d = site.distance(f.geom)
        key = f.label or ""
        if key in by_label:
            it = by_label[key]
            it.count += 1
            if d < it.distance_m:
                it.distance_m, it.direction = d, bearing_word(site, f.geom)
        else:
            by_label[key] = Item(f.label, d, bearing_word(site, f.geom))
    items = sorted(by_label.values(), key=lambda i: (i.distance_m, i.label))
    # Unlabelled pieces of one dataset (e.g. surface-water extents) read as
    # one line: "Unnamed area (14 parcels), within the red line".
    return items


def build_findings(results: List[LayerResult], site: BaseGeometry) -> List[LayerFinding]:
    out = []
    for r in results:
        lf = LayerFinding(r.layer.id, r.layer.name, r.layer.group, r.status, r.layer.search_m,
                          partial_coverage=r.partial_coverage, note=r.layer.note, error=r.error)
        if r.status == PRESENT:
            lf.items = _items(r, site)
            lf.on_site = any(i.distance_m <= ON_SITE_TOLERANCE_M for i in lf.items)
        out.append(lf)
    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(out, key=lambda f: order.get(f.group, 99))  # stable within group


def counts(findings: List[LayerFinding]) -> Dict[str, int]:
    c = {PRESENT: 0, NONE_FOUND: 0, NOT_ASSESSED: 0}
    for f in findings:
        c[f.status] += 1
    return c
