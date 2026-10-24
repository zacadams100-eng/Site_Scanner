"""
Optional OS basemap (OS Maps API, Light style, British National Grid).

Only zoom levels 0–9 are OS OpenData; 10+ are Premium and are never
requested, so a free OS Data Hub key is enough. Without a key — or if the
tiles fail — the sheet still renders, on a plain 1 km grid, and says so.

Tile matrix: origin (-238375, 1376256), 256 px tiles, 896 m/px at zoom 0
halving each level (OS Maps API EPSG:27700). Check against the OS docs if
tiles ever appear offset.
"""

import io
import os
from typing import Optional, Tuple

import numpy as np
import requests

URL = "https://api.os.uk/maps/raster/v1/zxy/Light_27700/{z}/{x}/{y}.png"
ORIGIN_X, ORIGIN_Y = -238375.0, 1376256.0
TILE = 256
MAX_OPEN_ZOOM = 9
ATTRIBUTION = "Contains OS data © Crown copyright and database rights {year}"


def res(z: int) -> float:
    return 896.0 / (2 ** z)


def pick_zoom(m_per_px_needed: float) -> int:
    """Finest open zoom that is not much finer than the print needs."""
    for z in range(MAX_OPEN_ZOOM, -1, -1):
        if res(z) >= m_per_px_needed / 1.5:
            return z
    return 0


def fetch_basemap(extent: Tuple[float, float, float, float], m_per_px: float,
                  key: Optional[str] = None, session: Optional[requests.Session] = None
                  ) -> Optional[Tuple[np.ndarray, Tuple[float, float, float, float]]]:
    """Returns (image, (xmin, xmax, ymin, ymax)) for imshow, or None."""
    key = key or os.environ.get("OS_API_KEY")
    if not key:
        return None
    from PIL import Image

    s = session or requests.Session()
    z = pick_zoom(m_per_px)
    r = res(z)
    span = TILE * r
    xmin, ymin, xmax, ymax = extent
    c0, c1 = int((xmin - ORIGIN_X) // span), int((xmax - ORIGIN_X) // span)
    r0, r1 = int((ORIGIN_Y - ymax) // span), int((ORIGIN_Y - ymin) // span)
    if (c1 - c0 + 1) * (r1 - r0 + 1) > 120:
        return None  # refuse silly requests
    mosaic = np.ones(((r1 - r0 + 1) * TILE, (c1 - c0 + 1) * TILE, 3), dtype=np.uint8) * 255
    try:
        for row in range(r0, r1 + 1):
            for col in range(c0, c1 + 1):
                resp = s.get(URL.format(z=z, x=col, y=row), params={"key": key}, timeout=20)
                resp.raise_for_status()
                img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                y0, x0 = (row - r0) * TILE, (col - c0) * TILE
                mosaic[y0:y0 + TILE, x0:x0 + TILE] = np.asarray(img)
    except Exception:
        return None
    ext = (ORIGIN_X + c0 * span, ORIGIN_X + (c1 + 1) * span,
           ORIGIN_Y - (r1 + 1) * span, ORIGIN_Y - r0 * span)
    return mosaic, ext
