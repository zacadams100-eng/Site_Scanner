"""
Render the sheet: A4 landscape, map at a true printed scale, key, findings.

Page 1 — the map sheet: map frame at a standard scale, key of what is on
the map, headline findings, title block.
Page 2 — findings schedule: every layer, what was found and where, what was
not assessed and why, sources and licences, limitations.
"""

import datetime as dt
import textwrap
from typing import List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch, Patch, Polygon as MplPolygon, Rectangle
from matplotlib.path import Path as MplPath
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from . import basemap
from .fetch import NONE_FOUND, NOT_ASSESSED, PRESENT, LayerResult
from .findings import LayerFinding, counts
from .geometry import area_ha, search_area
from .layers import GROUPS, LAYER_BY_ID

MM = 1 / 25.4  # inches per mm
PAGE_W, PAGE_H = 297, 210
MARGIN = 8
MAP_W, MAP_H = 190, 194
PANEL_X = MARGIN + MAP_W + 5
PANEL_W = PAGE_W - PANEL_X - MARGIN

INK = "#1c1f1d"
MUTED = "#6b6f69"
RULE = "#c9c6bd"
FOREST = "#1f3d2b"
RED = "#e41a1c"

SCALES = [1250, 2500, 5000, 10000, 12500, 25000, 50000, 100000]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 6.5, "pdf.fonttype": 42,
                     "hatch.linewidth": 0.45})

# Back to front. Big context areas first, small or point features last.
DRAW_ORDER = [
    "green_belt", "national_park", "national_landscape", "nia", "lnrs", "gcn_soa",
    "woodland", "common_land", "local_green_space", "priority_habitat",
    "flood_zone", "surface_water", "flood_storage", "ancient_woodland",
    "sac", "spa", "ramsar", "sssi", "nnr", "lnr",
    "conservation_area", "park_garden", "scheduled_monument", "tpo_area",
    "main_river", "listed_building", "tpo_tree",
]


def choose_scale(site: BaseGeometry, display_m: float) -> int:
    minx, miny, maxx, maxy = site.bounds
    need_w = (maxx - minx) + 2 * display_m
    need_h = (maxy - miny) + 2 * display_m
    for s in SCALES:
        if MAP_W * s / 1000 >= need_w and MAP_H * s / 1000 >= need_h:
            return s
    return SCALES[-1]


def map_extent(site: BaseGeometry, scale: int) -> Tuple[float, float, float, float]:
    c = site.centroid
    w, h = MAP_W * scale / 1000, MAP_H * scale / 1000
    return c.x - w / 2, c.y - h / 2, c.x + w / 2, c.y + h / 2


# --- shapely → matplotlib -----------------------------------------------------
def _ring_path(coords):
    verts = list(coords)
    codes = [MplPath.MOVETO] + [MplPath.LINETO] * (len(verts) - 2) + [MplPath.CLOSEPOLY]
    return verts, codes


def _poly_path(geom) -> Optional[MplPath]:
    verts, codes = [], []
    polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
    for p in polys:
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        for ring in [p.exterior, *p.interiors]:
            v, c = _ring_path(ring.coords)
            verts += v
            codes += c
    return MplPath(verts, codes) if verts else None


def _draw(ax, geom: BaseGeometry, style, z: float, kind: str):
    if geom.is_empty:
        return
    gt = geom.geom_type
    if gt == "GeometryCollection":
        for g in geom.geoms:
            _draw(ax, g, style, z, kind)
        return
    if gt in ("Polygon", "MultiPolygon"):
        path = _poly_path(geom)
        if path is None:
            return
        face = "none" if style.fill == "none" else style.fill
        if face != "none":
            ax.add_patch(PathPatch(path, facecolor=face, alpha=style.alpha, edgecolor="none", zorder=z))
        ax.add_patch(PathPatch(path, facecolor="none", edgecolor=style.edge, lw=style.width,
                               hatch=style.hatch, zorder=z + 0.1))
    elif gt in ("LineString", "MultiLineString", "LinearRing"):
        lines = [geom] if gt != "MultiLineString" else list(geom.geoms)
        for ln in lines:
            xs, ys = ln.xy
            ax.plot(xs, ys, color=style.edge, lw=style.width, zorder=z, solid_capstyle="round")
    elif gt in ("Point", "MultiPoint"):
        pts = [geom] if gt == "Point" else list(geom.geoms)
        ax.scatter([p.x for p in pts], [p.y for p in pts], s=10, marker=style.marker,
                   facecolor=style.fill, edgecolor=style.edge, linewidths=style.width, zorder=z)


def _swatch(style, kind: str):
    if kind == "line":
        return Line2D([0], [0], color=style.edge, lw=style.width + 0.4)
    if kind == "point":
        return Line2D([0], [0], marker=style.marker, color="none", markerfacecolor=style.fill,
                      markeredgecolor=style.edge, markersize=4)
    face = "none" if style.fill == "none" else style.fill
    return Patch(facecolor=face, edgecolor=style.edge, hatch=style.hatch, lw=style.width,
                 alpha=None if face == "none" else max(style.alpha, 0.5))


# --- page furniture ------------------------------------------------------------
def _north_arrow(fig, x_mm, y_mm):
    ax = fig.add_axes([x_mm * MM / (PAGE_W * MM), y_mm / PAGE_H, 8 / PAGE_W, 12 / PAGE_H])
    ax.set_axis_off()
    ax.add_patch(MplPolygon([[0.5, 1], [0.15, 0.2], [0.5, 0.4]], color=INK))
    ax.add_patch(MplPolygon([[0.5, 1], [0.85, 0.2], [0.5, 0.4]], facecolor="white", edgecolor=INK, lw=0.6))
    ax.text(0.5, 0.0, "N", ha="center", va="center", fontsize=7, weight="bold")
    ax.set_xlim(0, 1)
    ax.set_ylim(-0.15, 1.05)


def _scale_bar(ax, extent, scale):
    xmin, ymin, xmax, ymax = extent
    nice = [50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000]
    target = (xmax - xmin) * 0.25
    L = max(n for n in nice if n <= target) if any(n <= target for n in nice) else nice[0]
    x0, y0 = xmin + (xmax - xmin) * 0.03, ymin + (ymax - ymin) * 0.03
    h = (ymax - ymin) * 0.008
    ax.add_patch(Rectangle((x0 - L * 0.04, y0 - h * 1.5), L * 1.08, h * 6.3, facecolor="white",
                           edgecolor="none", alpha=0.85, zorder=50))
    for i in range(4):
        ax.add_patch(Rectangle((x0 + i * L / 4, y0), L / 4, h, facecolor=INK if i % 2 == 0 else "white",
                               edgecolor=INK, lw=0.5, zorder=51))
    lbl = lambda v: f"{v:,.0f} m" if L < 1000 else f"{v / 1000:g} km"
    ax.text(x0, y0 + h * 1.6, "0", fontsize=5.5, zorder=52, ha="center")
    ax.text(x0 + L, y0 + h * 1.6, lbl(L), fontsize=5.5, zorder=52, ha="center")
    ax.text(x0 + L / 2, y0 + h * 3.3, f"1:{scale:,} at A4", fontsize=5.5, zorder=52, ha="center")


def _grid(ax, extent, step):
    xmin, ymin, xmax, ymax = extent
    import math
    for x in range(int(math.ceil(xmin / step) * step), int(xmax) + 1, step):
        ax.axvline(x, color="#000000", lw=0.2, alpha=0.18, zorder=0.5)
    for y in range(int(math.ceil(ymin / step) * step), int(ymax) + 1, step):
        ax.axhline(y, color="#000000", lw=0.2, alpha=0.18, zorder=0.5)


def _wrap(s: str, width: int) -> List[str]:
    return textwrap.wrap(s, width=width) or [""]


def _watermark(fig):
    fig.text(0.5, 0.5, "TEST DATA — NOT REAL — NOT FOR CLIENT USE", rotation=28, fontsize=34,
             color=RED, alpha=0.22, ha="center", va="center", weight="bold", zorder=100)


def _title_block(fig, meta):
    top = PAGE_H - MARGIN
    h = 30
    fig.patches.append(Rectangle((PANEL_X * MM, (top - h) * MM), PANEL_W * MM, h * MM,
                                 transform=fig.dpi_scale_trans, facecolor=FOREST, edgecolor="none"))
    t = lambda y, s, **k: fig.text((PANEL_X + 3) / PAGE_W, y / PAGE_H, s, color="white", **k)
    t(top - 5, "CONTOUR · DESK STUDY MAP", fontsize=5.5, weight="bold", family="DejaVu Sans Mono")
    for i, line in enumerate(_wrap(meta["title"], 30)[:2]):
        t(top - 11 - i * 5, line, fontsize=9.5, weight="bold")
    t(top - 23, meta["subtitle"], fontsize=6)
    t(top - 27, meta["ref_line"], fontsize=5.5, family="DejaVu Sans Mono")
    return top - h


def _section(fig, y, title):
    fig.text((PANEL_X) / PAGE_W, y / PAGE_H, title.upper(), fontsize=5.5, weight="bold",
             color=MUTED, family="DejaVu Sans Mono")
    fig.add_artist(Line2D([PANEL_X / PAGE_W, (PANEL_X + PANEL_W) / PAGE_W],
                          [(y - 1.5) / PAGE_H] * 2, color=RULE, lw=0.5))
    return y - 4.5


# --- the sheet ------------------------------------------------------------------
def render_sheet(path, site: BaseGeometry, results: List[LayerResult], findings: List[LayerFinding],
                 title: str, client_ref: str = "", display_m: float = 500,
                 os_key: Optional[str] = None, made_at: Optional[dt.datetime] = None) -> dict:
    made_at = made_at or dt.datetime.now()
    scale = choose_scale(site, display_m)
    extent = map_extent(site, scale)
    ext_box = box(*extent)
    fixture = any(r.fixture for r in results)
    c = counts(findings)

    meta = {
        "title": title,
        "subtitle": f"Red line {area_ha(site):,.2f} ha · centred {site.centroid.x:,.0f} E, {site.centroid.y:,.0f} N",
        "ref_line": " · ".join(x for x in [client_ref, made_at.strftime("%d %b %Y %H:%M"), f"1:{scale:,}"] if x),
    }

    with PdfPages(path) as pdf:
        # ===== Page 1: map sheet =====
        fig = plt.figure(figsize=(PAGE_W * MM, PAGE_H * MM))
        ax = fig.add_axes([MARGIN / PAGE_W, MARGIN / PAGE_H, MAP_W / PAGE_W, MAP_H / PAGE_H])
        xmin, ymin, xmax, ymax = extent
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_linewidth(0.8)
            sp.set_color(INK)

        m_per_px = scale / 1000 * 25.4 / 200  # ground metres per printed pixel at 200 dpi
        bm = basemap.fetch_basemap(extent, m_per_px, key=os_key)
        if bm:
            img, e = bm
            ax.imshow(img, extent=e, zorder=0, interpolation="bilinear", alpha=0.75)
        else:
            ax.set_facecolor("#fbfaf6")
        _grid(ax, extent, 1000 if scale >= 10000 else (500 if scale >= 5000 else 100))

        simplify = scale * 0.2 / 1000  # 0.2 mm on paper
        by_id = {r.layer.id: r for r in results}
        on_map = []
        for z, lid in enumerate(DRAW_ORDER):
            r = by_id.get(lid)
            if not r or r.status != PRESENT or not r.layer.on_map:
                continue
            shown = False
            for f in r.features:
                if not f.geom.intersects(ext_box):
                    continue
                g = f.geom.intersection(ext_box.buffer(scale * 0.01)).simplify(simplify)
                _draw(ax, g, r.layer.style, 2 + z, r.layer.geom)
                shown = True
            if shown:
                on_map.append(r.layer)

        # search rings and the red line, always on top
        for d in (1000, 2000):
            ring = search_area(site, d).boundary
            for part in ([ring] if ring.geom_type in ("LineString", "LinearRing") else list(ring.geoms)):
                if part.intersects(ext_box):
                    xs, ys = part.xy
                    ax.plot(xs, ys, color=INK, lw=0.5, ls=(0, (4, 3)), zorder=40, alpha=0.6)
        for p in ([site] if site.geom_type == "Polygon" else list(site.geoms)):
            xs, ys = p.exterior.xy
            ax.plot(xs, ys, color="white", lw=3.2, zorder=44)
            ax.plot(xs, ys, color=RED, lw=1.6, zorder=45)
        _scale_bar(ax, extent, scale)
        _north_arrow(fig, MARGIN + MAP_W - 12, MARGIN + MAP_H - 16)
        if not bm:
            ax.text(xmax - (xmax - xmin) * 0.01, ymin + (ymax - ymin) * 0.01,
                    "No basemap · 1 km grid shown", fontsize=4.8, color=MUTED, ha="right", zorder=52)

        # --- right panel ---
        y = _title_block(fig, meta) - 6
        y = _section(fig, y, "Key")
        key_items = [(Line2D([0], [0], color=RED, lw=1.6), "Red line (site boundary)"),
                     (Line2D([0], [0], color=INK, lw=0.6, ls=(0, (4, 3))), "1 km and 2 km from red line")]
        key_items += [(_swatch(l.style, l.geom), l.name) for l in on_map]
        rows = len(key_items)
        kh = rows * 3.55 + 1
        kax = fig.add_axes([PANEL_X / PAGE_W, (y - kh) / PAGE_H, PANEL_W / PAGE_W, kh / PAGE_H])
        kax.set_axis_off()
        kax.legend([k[0] for k in key_items], [k[1] for k in key_items], loc="upper left",
                   frameon=False, fontsize=5.8, handlelength=2.2, handleheight=1.0,
                   labelspacing=0.45, borderaxespad=0, borderpad=0)
        y -= kh + 4

        y = _section(fig, y, "Findings")
        on_site = [f for f in findings if f.on_site]
        lines = [f"{c[PRESENT]} layers present · {c[NONE_FOUND]} none found · {c[NOT_ASSESSED]} not assessed"]
        if on_site:
            lines.append("Within the red line: " + ", ".join(f.name for f in on_site) + ".")
        else:
            lines.append("No mapped constraint falls within the red line.")
        nearest = sorted((f for f in findings if f.status == PRESENT and not f.on_site and f.items),
                         key=lambda f: f.items[0].distance_m)[:4]
        for f in nearest:
            if f.areas:   # parcel layers read as hectares, not "unnamed, 30 m"
                lines.append(f"{f.name}: {f.summary(max_items=2)}")
            else:
                lines.append(f"{f.name}: {f.items[0].label or 'unnamed'}, {f.items[0].where()}.")
        lines.append("Full schedule overleaf.")
        for ln in lines:
            for w in _wrap(ln, 62):
                if y < 52:
                    break
                fig.text(PANEL_X / PAGE_W, y / PAGE_H, w, fontsize=5.8, color=INK)
                y -= 3.0
            y -= 0.8

        # footer: screening notice + sources
        fy = MARGIN + 34
        fig.patches.append(Rectangle((PANEL_X * MM, (MARGIN + 18) * MM), PANEL_W * MM, 18 * MM,
                                     transform=fig.dpi_scale_trans, facecolor="#efece4", edgecolor="none"))
        fig.text(PANEL_X / PAGE_W + 0.008, (fy - 1) / PAGE_H, "SCREENING ONLY", fontsize=5.5,
                 weight="bold", family="DejaVu Sans Mono", color=INK)
        notice = ("Statutory and published datasets only. Not a records-centre search, field survey "
                  "or legal advice. Search radii are product defaults, not regulatory thresholds.")
        for i, w in enumerate(_wrap(notice, 64)):
            fig.text(PANEL_X / PAGE_W + 0.008, (fy - 4.5 - i * 2.8) / PAGE_H, w, fontsize=5.2, color=INK)
        src = (f"Data read live {made_at:%d %b %Y}: Natural England, Environment Agency, Historic England, "
               "Forestry Commission, Defra, local planning authorities via planning.data.gov.uk. "
               "Contains public sector information licensed under the Open Government Licence v3.0.")
        if bm:
            src += " " + basemap.ATTRIBUTION.format(year=made_at.year) + "."
        for i, w in enumerate(_wrap(src, 70)):
            fig.text(PANEL_X / PAGE_W, (MARGIN + 14 - i * 2.6) / PAGE_H, w, fontsize=4.6, color=MUTED)

        if fixture:
            _watermark(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # ===== Page 2: findings schedule =====
        _schedule_pages(pdf, findings, meta, made_at, fixture)

    return {"scale": scale, "extent": extent, "on_map": [l.id for l in on_map], "basemap": bool(bm),
            "fixture": fixture}


def _schedule_pages(pdf, findings, meta, made_at, fixture):
    col = [MARGIN, MARGIN + 62, MARGIN + 80]   # layer · radius · result
    result_chars = 150

    def new_page(n):
        fig = plt.figure(figsize=(PAGE_W * MM, PAGE_H * MM))
        fig.text(MARGIN / PAGE_W, (PAGE_H - MARGIN - 3) / PAGE_H, "FINDINGS SCHEDULE",
                 fontsize=6, weight="bold", color=MUTED, family="DejaVu Sans Mono")
        fig.text(MARGIN / PAGE_W, (PAGE_H - MARGIN - 9) / PAGE_H, meta["title"], fontsize=11, weight="bold")
        fig.text((PAGE_W - MARGIN) / PAGE_W, (PAGE_H - MARGIN - 3) / PAGE_H,
                 f"{meta['ref_line']} · page {n}", fontsize=5.5, ha="right", color=MUTED,
                 family="DejaVu Sans Mono")
        for x, h in zip(col, ["Layer", "Searched", "What the published data shows"]):
            fig.text(x / PAGE_W, (PAGE_H - MARGIN - 17) / PAGE_H, h, fontsize=5.8, weight="bold")
        fig.add_artist(Line2D([MARGIN / PAGE_W, (PAGE_W - MARGIN) / PAGE_W],
                              [(PAGE_H - MARGIN - 18.5) / PAGE_H] * 2, color=INK, lw=0.6))
        if fixture:
            _watermark(fig)
        return fig, PAGE_H - MARGIN - 23

    n = 2
    fig, y = new_page(n)
    current_group = None
    for f in findings:
        rlines = _wrap(f.summary(max_items=8), result_chars)
        if f.note and f.status != NOT_ASSESSED:
            rlines += _wrap(f"Note: {f.note}", result_chars)
        if f.status == NOT_ASSESSED and f.error:
            rlines += _wrap(f"Reason: {f.error}", result_chars)
        need = 3.0 * len(rlines) + (6 if f.group != current_group else 0) + 1.5
        if y - need < MARGIN + 6:
            pdf.savefig(fig)
            plt.close(fig)
            n += 1
            fig, y = new_page(n)
            current_group = None
        if f.group != current_group:
            y -= 1.5
            fig.text(col[0] / PAGE_W, y / PAGE_H, f.group.upper(), fontsize=5.5, weight="bold",
                     color=FOREST, family="DejaVu Sans Mono")
            y -= 4.0
            current_group = f.group
        colour = {PRESENT: INK, NONE_FOUND: MUTED, NOT_ASSESSED: RED}[f.status]
        fig.text(col[0] / PAGE_W, y / PAGE_H, f.name, fontsize=6, color=INK,
                 weight="bold" if f.on_site else "normal")
        radius = "red line" if f.search_m == 0 else (f"{f.search_m:,} m" if f.search_m < 1000 else f"{f.search_m // 1000} km")
        fig.text(col[1] / PAGE_W, y / PAGE_H, radius, fontsize=6, color=MUTED)
        for i, w in enumerate(rlines):
            fig.text(col[2] / PAGE_W, (y - i * 3.0) / PAGE_H, w, fontsize=6, color=colour if i == 0 else MUTED)
        y -= 3.0 * len(rlines) + 1.5
        fig.add_artist(Line2D([MARGIN / PAGE_W, (PAGE_W - MARGIN) / PAGE_W], [(y + 1.6) / PAGE_H] * 2,
                              color=RULE, lw=0.3))

    # limitations block at the foot of the last page
    lim = [
        "How to read this schedule. 'None found' means the publisher was queried and returned nothing in the "
        "search radius. 'Not assessed' means the query failed — it is not a clear result. Layers supplied by local "
        "planning authorities (conservation areas, tree preservation orders, Green Belt, local green space) are not "
        "yet published by every council, so a nil return there must be confirmed with the council.",
        "This sheet does not include protected or notable species records, local wildlife sites or other "
        "non-statutory designations held by local environmental records centres, which a Preliminary Ecological "
        "Appraisal normally requires. Distances are measured from the red line to the nearest edge of each feature "
        "in British National Grid. Data was read from each publisher at the moment the sheet was made "
        f"({made_at:%d %b %Y %H:%M}) and may have changed since.",
    ]
    lim_lines = [_wrap(p, 210) for p in lim]
    lim_h = sum(2.7 * len(l) + 1.5 for l in lim_lines) + 4
    if y - lim_h < MARGIN:
        pdf.savefig(fig)
        plt.close(fig)
        n += 1
        fig, y = new_page(n)
    yy = y - 3
    for para in lim:
        for w in _wrap(para, 210):
            fig.text(MARGIN / PAGE_W, yy / PAGE_H, w, fontsize=5.4, color=MUTED)
            yy -= 2.7
        yy -= 1.5
    pdf.savefig(fig)
    plt.close(fig)
