"""Per-client request limiting.

The API is public and unauthenticated, every `/api/series` call can reach
Earth Engine or five government endpoints, and Earth Engine has a compute
quota that is shared across everyone using this app. One script in a loop can
therefore spend a quota that belongs to every other user, and until now
nothing stopped it.

**What this is not.** The counters live in the process, so on Vercel — where
requests are spread across instances that are recycled freely — the effective
limit is per instance, not per deployment. That makes this a guard against one
client hammering one instance, not a global budget. A real budget needs shared
state (Redis, or Vercel KV), which is a dependency and an account, and
`DEPLOY.md` already makes the same argument about the response cache. The
simplest thing that works is documented rather than dressed up: see
`PROGRESS.md`.

**Why a sliding window rather than a token bucket.** A bucket lets a client
spend its whole allowance instantly and then starve, which for an interactive
map means the fourth shape you draw fails while you are watching. A window
sized in requests-per-minute degrades more gently at the boundary that
actually matters here.

Costs are per-route because the routes are not comparable: `/api/catalog` is
one cached dictionary, `/api/series` can be twenty-four upstream calls.
Charging them the same either throttles browsing or fails to throttle work.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

# Requests per window. Generous for a person drawing shapes, cheap to exceed
# with a script: a browser session costs perhaps 30 units a minute at its
# busiest, so the default leaves ample headroom for real use.
WINDOW_SECONDS = float(os.environ.get("RATE_LIMIT_WINDOW", "60"))
BUDGET = float(os.environ.get("RATE_LIMIT_BUDGET", "120"))

# What each route costs against the budget. Anything unlisted costs 1.
ROUTE_COST: Dict[str, float] = {
    "/api/series": 6.0,   # up to 24 factors, each potentially an upstream call
    "/api/ask": 6.0,      # same work, reached a different way
    "/api/cells": 2.0,
    "/api/summary": 4.0,  # may call an LLM
    "/api/stats": 3.0,
    "/api/catalog": 0.5,  # a cached dictionary; browsing must stay free
}

# Bound the number of tracked clients so a spray of forged X-Forwarded-For
# values cannot grow this without limit — that would turn the protection into
# the memory leak it exists to prevent.
MAX_CLIENTS = 4096


def cost_for(path: str) -> float:
    for prefix, cost in ROUTE_COST.items():
        if path == prefix or path.startswith(prefix + "/"):
            return cost
    return 1.0


def client_key(headers: Dict[str, str], fallback: Optional[str]) -> str:
    """Identify the caller.

    Behind Vercel and Cloud Run the socket address is the proxy, so the real
    client is the first entry of X-Forwarded-For. That header is trivially
    forged, which is exactly why MAX_CLIENTS exists: a forged value costs the
    forger their own bucket and costs us a bounded amount of memory.
    """
    forwarded = headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return headers.get("x-real-ip") or fallback or "unknown"


class SlidingWindow:
    """Cost-weighted sliding window, safe across threads."""

    def __init__(self, budget: float = BUDGET, window: float = WINDOW_SECONDS,
                 max_clients: int = MAX_CLIENTS):
        self.budget = budget
        self.window = window
        self.max_clients = max_clients
        self._hits: Dict[str, Deque[Tuple[float, float]]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> Deque[Tuple[float, float]]:
        hits = self._hits.setdefault(key, deque())
        cutoff = now - self.window
        while hits and hits[0][0] <= cutoff:
            hits.popleft()
        return hits

    def check(self, key: str, cost: float = 1.0,
              now: Optional[float] = None) -> Tuple[bool, float, float]:
        """(allowed, remaining, retry_after_seconds).

        A rejected request is not recorded. Counting it would let a client that
        is already over the limit hold itself over indefinitely by continuing
        to retry, which turns a soft limit into a permanent ban.
        """
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._prune(key, now)
            spent = sum(c for _, c in hits)

            if spent + cost > self.budget:
                oldest = hits[0][0] if hits else now
                retry_after = max(0.0, self.window - (now - oldest))
                return False, max(0.0, self.budget - spent), retry_after

            hits.append((now, cost))

            if len(self._hits) > self.max_clients:
                self._evict(now)

            return True, max(0.0, self.budget - spent - cost), 0.0

    def _evict(self, now: float) -> None:
        """Drop clients with nothing left in the window, then oldest-first.

        Called with the lock held.
        """
        for key in [k for k, v in self._hits.items()
                    if not v or v[-1][0] <= now - self.window]:
            del self._hits[key]

        if len(self._hits) > self.max_clients:
            ordered = sorted(self._hits.items(), key=lambda kv: kv[1][-1][0])
            for key, _ in ordered[: len(self._hits) - self.max_clients]:
                del self._hits[key]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


LIMITER = SlidingWindow()


def install(app, limiter: Optional[SlidingWindow] = None) -> None:
    """Attach the limiter to a FastAPI app.

    Only `/api/*` is limited. Everything else on these apps is a health check
    or, in the Cloud Run case, nothing at all — and on Vercel the static files
    never reach Python.
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse

    bucket = limiter or LIMITER

    @app.middleware("http")
    async def _rate_limit(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        headers = {k.lower(): v for k, v in request.headers.items()}
        key = client_key(headers, request.client.host if request.client else None)
        allowed, remaining, retry_after = bucket.check(key, cost_for(path))

        if not allowed:
            return JSONResponse(
                status_code=429,
                # `detail` because that is the field the frontend already
                # surfaces verbatim for anything a user can act on.
                content={"detail": ("Too many requests from this address. "
                                    f"Try again in {int(retry_after) + 1}s.")},
                headers={
                    "Retry-After": str(int(retry_after) + 1),
                    "X-RateLimit-Limit": str(int(bucket.budget)),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(int(bucket.budget))
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        return response
