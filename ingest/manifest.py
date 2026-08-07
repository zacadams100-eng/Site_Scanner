"""
Ingest manifests — declarative dataset definitions.

One manifest per base dataset; one generic runner executes all of them. The
point is that adding a dataset should be writing 20 lines of YAML, not writing
another bespoke script — which is how ingest codebases usually rot.

Each manifest declares where the data comes from, how to derive it, the grid
it lands on, and what outputs to produce. The runner does the rest.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Temporal:
    step: str                      # 'monthly' | 'annual' | 'static'
    start: Optional[str] = None    # 'YYYY-MM'
    end: Optional[str] = None

    def __post_init__(self) -> None:
        if self.step not in ("monthly", "annual", "static"):
            raise ValueError(f"temporal.step must be monthly/annual/static, got {self.step!r}")
        if self.step != "static" and not (self.start and self.end):
            raise ValueError(f"temporal.step={self.step} requires start and end")


@dataclass
class Spatial:
    resolution_m: float
    crs: str = "EPSG:27700"        # British National Grid — equal-area enough
                                   # for England, and what UK data ships in.
    bbox: Optional[List[float]] = None


@dataclass
class Storage:
    """How a continuous raster is quantised on disk.

    `scale` follows GDAL exactly: `value = raw * scale + offset`. So 0.0001
    stores four decimal places, and the representable range is
    [-32767 x scale + offset, 32767 x scale + offset] — 0.0001 gives
    +/-3.2767, which covers any index bounded to [-1, 1] with room to spare.

    Storing continuous data as int16 rather than float32 is a 3-6x saving on
    every byte this project will ever pay to keep; docs/INGEST-BENCHMARK.md
    Result 5 has the measurements. `dtype: float32` opts out for a raster
    whose range genuinely needs it, and says so in the manifest rather than
    by accident.
    """
    dtype: str = "int16"
    scale: float = 0.0001
    offset: float = 0.0

    def __post_init__(self) -> None:
        if self.dtype not in ("int16", "float32"):
            raise ValueError(f"storage.dtype must be int16/float32, got {self.dtype!r}")
        if self.dtype == "int16" and self.scale <= 0:
            raise ValueError(f"storage.scale must be positive, got {self.scale!r}")

    @property
    def write_scale(self) -> Optional[float]:
        """What to hand `write_cog`. None means "write it as it comes"."""
        return self.scale if self.dtype == "int16" else None

    def span(self) -> tuple:
        """The values this quantisation can hold, for error messages."""
        return (-32767 * self.scale + self.offset, 32767 * self.scale + self.offset)


@dataclass
class Manifest:
    id: str
    kind: str                      # 'continuous' | 'categorical'
    unit: str
    source: Dict[str, Any]
    temporal: Temporal
    spatial: Spatial
    h3_resolutions: List[int] = field(default_factory=lambda: [7, 8])
    nodata: Optional[float] = None
    storage: Storage = field(default_factory=Storage)

    def __post_init__(self) -> None:
        if self.kind not in ("continuous", "categorical"):
            raise ValueError(f"kind must be continuous/categorical, got {self.kind!r}")
        if not self.h3_resolutions:
            raise ValueError("at least one h3 resolution is required")
        # The benchmark showed res 8 is right up to 250 km2 and res 7 above it;
        # a manifest that stores only one tier will be slow at one end or
        # coarse at the other. See BENCHMARK.md.
        bad = [r for r in self.h3_resolutions if not 5 <= r <= 9]
        if bad:
            raise ValueError(f"h3 resolutions out of range: {bad}")

    @classmethod
    def load(cls, path: Path) -> "Manifest":
        raw = yaml.safe_load(Path(path).read_text())
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "Manifest":
        missing = {"id", "kind", "unit", "source", "temporal", "spatial"} - set(raw)
        if missing:
            raise ValueError(f"manifest is missing: {', '.join(sorted(missing))}")
        return cls(
            id=raw["id"],
            kind=raw["kind"],
            unit=raw["unit"],
            source=raw["source"],
            temporal=Temporal(**raw["temporal"]),
            spatial=Spatial(**raw["spatial"]),
            h3_resolutions=raw.get("h3_resolutions", [7, 8]),
            nodata=raw.get("nodata"),
            # Continuous rasters quantise by default; a manifest has to opt
            # out deliberately rather than get float32 by forgetting.
            storage=Storage(**(raw.get("storage") or {})),
        )

    def timesteps(self) -> List[str]:
        """Every timestep this manifest covers, as 'YYYY-MM'."""
        if self.temporal.step == "static":
            return ["static"]
        sy, sm = (int(x) for x in self.temporal.start.split("-"))
        ey, em = (int(x) for x in self.temporal.end.split("-"))
        out: List[str] = []
        y, m = sy, sm
        while (y, m) <= (ey, em):
            out.append(f"{y:04d}-{m:02d}")
            if self.temporal.step == "annual":
                y += 1
            else:
                m += 1
                if m > 12:
                    m, y = 1, y + 1
        return out

    def asset_key(self, timestep: str, tile: str = "-") -> str:
        """Where this timestep's COG lives in object storage.

        A tiled run gets one file per tile, keyed by the tile's grid position,
        so the layout stays browsable and a tile can be re-fetched on its own.
        An untiled run keeps the flat path it always had — the tile id '-'
        means "the whole extent", and adding a '-' to those filenames would
        invalidate every path already written.
        """
        stem = f"{self.id}/static" if timestep == "static" else \
            "{}/{}/{}".format(self.id, *timestep.split("-"))
        return f"{stem}.tif" if tile == "-" else f"{stem}/{tile}.tif"
