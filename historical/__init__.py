"""
Historical evidence — Sentinel-2 and MODIS observations as temporal metrics.

`HISTORICAL_EVIDENCE_MODEL.md` is the specification and was written before any
of this. The rule it exists to enforce:

    Historical analysis is an evidence source, not a finding system.

This package produces **metrics**. A metric says what happened; a rule says
whether that crosses a defined threshold; the existing engine turns that into a
finding. Nothing here knows what `flagged` means, and nothing here should ever
need to.
"""

from historical.metrics import (                          # noqa: F401
    METHOD_VERSION,
    SEASONS,
    change_metric,
    coverage,
    usable_years,
)
