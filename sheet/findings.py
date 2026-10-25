"""
Turn layer results into plain findings.

A finding states what the published data shows and where — "Box Hill SSSI,
450 m NE". It never grades the site, scores it, or says whether a proposal
is acceptable. That judgement belongs to the ecologist reading the sheet.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List

from shapely.geometry.base import BaseGeometry

from .fetch import NONE_FOUND, NOT_ASSESSED, PRESENT, LayerResult
from .geometry import bearing_word, search_area
from .layers import GROUPS

ON_SITE_TOLERANCE_M = 0.5   # survey slop: touching the line counts as on site


@dataclass
class Item:
    label: str
    distance_m: float           # 0 = within or touching the red line
    direction: str
    count: int = 1              # polygons sharing this label
    grade: str = ""

    def where(self) -> str:
        if self.distance_m <= ON_SITE_TOLERANCE_M:
            return "within the red line"
        d = self.distance_m
        dist = f"{d:,.0f} m" if d < 1000 else f"{d / 1000:.1f} km"
        return f"{dist} {self.direction}".strip()


def fmt_ha(ha: float) -> str:
    if ha < 0.1:
        return "under 0.1 ha"
    return f"{ha:.1f} ha" if ha < 10 else f"{ha:,.0f} ha"


@dataclass
class AreaItem:
    label: str
    ha_in_radius: float
    ha_on_site: float


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
    # Area-mode layers only (summary="area" in layers.py).
    areas: List[AreaItem] = field(default_factory=list)
    site_ha: float = 0.0
    labelled: bool = True
    mode: str = "list"
    count_parcels: bool = True

    def summary(self, max_items: int = 3) -> str:
        if self.status == NOT_ASSESSED:
            return "Not assessed — data could not be retrieved."
        radius = "the red line" if self.search_m == 0 else f"{self._radius()} of the red line"
        if self.status == NONE_FOUND:
            s = f"None found within {radius}."
            if self.partial_coverage:
                s += " Published data is incomplete for some councils — confirm locally."
            return s
        if self.areas:
            return self._area_summary(max_items)
        if self.mode == "grades" and len(self.items) > 5:
            return self._grade_summary(max_items)
        if self.mode == "zones":
            return self._zone_summary()
        parts = []
        for it in self.items[:max_items]:
            name = it.label or "Unnamed area"
            if it.count > 1 and self.count_parcels:
                name += f" ({it.count} parcels)"
            parts.append(f"{name}, {it.where()}")
        more = len(self.items) - max_items
        if more > 0:
            parts.append(f"+{more} more")
        return "; ".join(parts) + "."

    def _area_summary(self, max_items: int) -> str:
        """Hectares by type, and how much of the red line is covered.

        "Surface water flooding: covers 6% of the red line (0.4 ha)" says
        something; "Unnamed area (2,430 parcels)" does not.
        """
        on_site = sum(a.ha_on_site for a in self.areas)
        parts = []
        if not self.labelled:
            if on_site > 0:
                pct = 100 * on_site / self.site_ha if self.site_ha else 0
                share = "under 1%" if pct < 1 else f"{pct:.0f}%"
                parts.append(f"Covers {share} of the red line ({fmt_ha(on_site)})")
            else:
                near = self.items[0]
                parts.append(f"Not on the red line; nearest {near.where()}")
            total = sum(a.ha_in_radius for a in self.areas)
            parts.append(f"{fmt_ha(total)} within {self._radius()}")
            return "; ".join(parts) + "."
        here = sorted((a for a in self.areas if a.ha_on_site > 0), key=lambda a: -a.ha_on_site)
        if here:
            parts.append("Within the red line: " + ", ".join(
                f"{a.label} {fmt_ha(a.ha_on_site)}" for a in here[:max_items]))
        elif self.items:
            parts.append(f"Nearest: {self.items[0].label or 'unnamed'}, {self.items[0].where()}")
        around = sorted(self.areas, key=lambda a: -a.ha_in_radius)
        text = ", ".join(f"{a.label} {fmt_ha(a.ha_in_radius)}" for a in around[:max_items + 1])
        more = len(around) - (max_items + 1)
        if more > 0:
            text += f", +{more} more type{'s' if more > 1 else ''}"
        parts.append(f"Within {self._radius()}: {text}")
        return ". ".join(parts) + "."

    def _grade_summary(self, max_items: int) -> str:
        """"178 within 500 m: 2 Grade I, 6 Grade II*, 170 Grade II", then by
        name only the highest grades and anything on the red line itself."""
        n = sum(i.count for i in self.items)
        by_grade: Dict[str, int] = {}
        for i in self.items:
            by_grade[i.grade or "ungraded"] = by_grade.get(i.grade or "ungraded", 0) + i.count
        order = {"I": 0, "II*": 1, "II": 2}
        grades = sorted(by_grade, key=lambda g: (order.get(g, 9), g))
        head = f"{n} within {self._radius()}: " + ", ".join(
            f"{by_grade[g]} Grade {g}" if g != "ungraded" else f"{by_grade[g]} ungraded" for g in grades)
        named = [i for i in self.items if i.grade in ("I", "II*") or i.distance_m <= ON_SITE_TOLERANCE_M]
        if not named:
            return head + "."
        shown = "; ".join(f"{i.label}, {i.where()}" for i in named[:max_items])
        more = len(named) - max_items
        return f"{head}. {shown}" + (f"; +{more} more" if more > 0 else "") + "."

    def _zone_summary(self) -> str:
        """Impact risk zones are not places; what matters is that the red line
        is in one, and where to read what it asks to be consulted on."""
        codes = []
        for i in self.items:
            m = re.search(r"irzcode=(\d+)", i.label or "")
            if m and m.group(1) not in codes:
                codes.append(m.group(1))
        # Count zones by code: one zone can arrive as several polygons.
        n = len(codes) or sum(i.count for i in self.items)
        head = f"The red line falls in {n} impact risk zone{'s' if n > 1 else ''}"
        if codes:
            head += f" (IRZ code{'s' if len(codes) > 1 else ''} {', '.join(codes[:4])}"
            head += f", +{len(codes) - 4} more)" if len(codes) > 4 else ")"
        return head + ". Check the consultation criteria for the proposal type at irz.geodata.org.uk."

    def _radius(self) -> str:
        m = self.search_m
        return f"{m:,} m" if m < 1000 else f"{m // 1000} km"


_FILLER = {"the", "and", "river", "conservation", "area", "of"}


def same_name_key(label: str) -> str:
    """One key for one place published twice under different spellings.

    Neighbouring councils both publish a shared conservation area:
    "RIVER WEY AND GODALMING NAVIGATIONS" and "Wey and Godalming Navigations"
    must read as one finding, not two.
    """
    words = re.findall(r"[a-z0-9*]+", label.lower().replace("&", " and "))
    return " ".join(w for w in words if w not in _FILLER) or label.lower()


def _items(result: LayerResult, site: BaseGeometry) -> List[Item]:
    by_label: Dict[str, Item] = {}
    # Buildings are separate things even when they share a name ("Barn").
    merge = result.layer.summary != "grades"
    for n, f in enumerate(result.features):
        d = site.distance(f.geom)
        key = same_name_key(f.label) if (merge and f.label) else (f.label if merge else str(n))
        if key in by_label:
            it = by_label[key]
            it.count += 1
            if d < it.distance_m:
                it.distance_m, it.direction = d, bearing_word(site, f.geom)
        else:
            by_label[key] = Item(f.label, d, bearing_word(site, f.geom), grade=f.grade)
    items = sorted(by_label.values(), key=lambda i: (i.distance_m, i.label))
    # An unnamed copy of a named feature (one council published a file name
    # where the other published the place) is the same finding, not another.
    named = [i.distance_m for i in items if i.label]
    items = [i for i in items if i.label or not any(abs(i.distance_m - d) < 5 for d in named)]
    # Unlabelled pieces of one dataset (e.g. surface-water extents) read as
    # one line: "Unnamed area (14 parcels), within the red line".
    return items


def _areas(result: LayerResult, site: BaseGeometry) -> List[AreaItem]:
    area = search_area(site, result.layer.search_m)
    by_label: Dict[str, AreaItem] = {}
    for f in result.features:
        key = f.label or "Unnamed"
        a = by_label.setdefault(key, AreaItem(key, 0.0, 0.0))
        a.ha_in_radius += f.geom.intersection(area).area / 10_000
        a.ha_on_site += f.geom.intersection(site).area / 10_000
    return list(by_label.values())


def build_findings(results: List[LayerResult], site: BaseGeometry) -> List[LayerFinding]:
    out = []
    for r in results:
        lf = LayerFinding(r.layer.id, r.layer.name, r.layer.group, r.status, r.layer.search_m,
                          partial_coverage=r.partial_coverage, note=r.layer.note, error=r.error,
                          mode=r.layer.summary, count_parcels=r.layer.count_parcels)
        if r.status == PRESENT:
            lf.items = _items(r, site)
            lf.on_site = any(i.distance_m <= ON_SITE_TOLERANCE_M for i in lf.items)
            if r.layer.summary == "area":
                lf.areas = _areas(r, site)
                lf.site_ha = site.area / 10_000
                lf.labelled = bool(r.layer.label_fields)
        out.append(lf)
    order = {g: i for i, g in enumerate(GROUPS)}
    return sorted(out, key=lambda f: order.get(f.group, 99))  # stable within group


def counts(findings: List[LayerFinding]) -> Dict[str, int]:
    c = {PRESENT: 0, NONE_FOUND: 0, NOT_ASSESSED: 0}
    for f in findings:
        c[f.status] += 1
    return c
