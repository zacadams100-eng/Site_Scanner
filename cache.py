"""
Contour — request cache
-----------------------
Earth Engine is free for this kind of use but metered, and `reduceRegion` over
a large polygon is slow. Redrawing the same shape, or nudging the year slider
back and forth, currently costs a fresh call every time. This is the simple
in-memory cache the README asks for.

Scope, honestly: this is per-process. Cloud Run runs several instances and
recycles them, so a cold instance always misses and two users drawing the same
field may not share an entry. It removes the obvious waste — one user
re-examining one site — and nothing more. A shared cache (Memorystore, or
Cloud Storage keyed by the same hash) is the thing that helps at scale.

Disable by setting CONTOUR_CACHE_TTL=0.
"""

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

DEFAULT_TTL_SECONDS = 900   # 15 minutes
DEFAULT_MAX_ENTRIES = 256


def cache_key(*parts: Any) -> str:
    """A stable key for any JSON-serialisable arguments.

    sort_keys matters: two identical polygons submitted with their keys in a
    different order must land on the same entry.
    """
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class TTLCache:
    """Small thread-safe LRU with expiry.

    FastAPI runs sync endpoints in a threadpool, so several requests can hit
    this concurrently — hence the lock.
    """

    def __init__(self, ttl: float = DEFAULT_TTL_SECONDS, max_entries: int = DEFAULT_MAX_ENTRIES):
        self.ttl = ttl
        self.max_entries = max_entries
        self._data: "OrderedDict[str, tuple]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    @property
    def enabled(self) -> bool:
        return self.ttl > 0 and self.max_entries > 0

    def get(self, key: str) -> Optional[Any]:
        if not self.enabled:
            self.misses += 1
            return None
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() >= expires_at:
                del self._data[key]        # expired; treat as a miss
                self.misses += 1
                return None
            self._data.move_to_end(key)    # refresh LRU position
            self.hits += 1
            return value

    def set(self, key: str, value: Any) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._data[key] = (value, time.monotonic() + self.ttl)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)   # evict least-recently-used

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
        self.hits = 0
        self.misses = 0

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)

    def info(self) -> dict:
        return {
            "enabled": self.enabled,
            "entries": len(self),
            "max_entries": self.max_entries,
            "ttl_seconds": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
        }


def _ttl_from_env() -> float:
    try:
        return float(os.environ.get("CONTOUR_CACHE_TTL", DEFAULT_TTL_SECONDS))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def build_cache() -> TTLCache:
    return TTLCache(ttl=_ttl_from_env())
