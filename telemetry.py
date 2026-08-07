"""Request latency, measured rather than assumed.

The whole product case rests on one claim — that a site screen takes seconds
where a desk study takes weeks — and until now nothing in the running system
could substantiate it. `/api/series` reported a per-factor `elapsed_ms`, but
nobody measured the request a user actually waits on: validation, the fan-out
across factors, the annual rollup, serialisation. A claim about speed that is
not instrumented is a claim that will eventually be wrong without anyone
noticing, because latency regressions do not raise exceptions.

So: every `/api/*` request is timed, the timing goes out on the response as
`Server-Timing` (which browser devtools plot natively, at no cost to us), a
structured line goes to the log, and `/api/metrics` serves the distribution.

**Three things this deliberately does not do.**

*It does not average.* A mean hides the tail, and the tail is the experience —
a p50 of 200 ms with a p95 of 9 s is a slow product that reports itself as a
fast one. Percentiles need the distribution kept, so a bounded ring of recent
samples is kept per route.

*It does not accumulate for ever.* `SAMPLES_PER_ROUTE` recent samples per
route, and a bounded number of routes. This is a diagnostic, not an analytics
warehouse, and an unbounded one on a long-lived process is a memory leak that
would eventually take down the thing it is measuring.

*It is per-process, and says so.* On Vercel the counters live in whichever
instance served the request and vanish when it is recycled, so `/api/metrics`
answers "how is this instance doing" and not "how is the deployment doing".
Aggregating across instances needs shared state — the same argument
`ratelimit.py` and `DEPLOY.md` already make about the response cache and the
rate limiter, and the same answer: the log line is the durable record, and
`/api/metrics` is the live one. `sampled_from` in the response says which it
is, so nobody quotes an instance figure as a deployment figure.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional

log = logging.getLogger("site_scanner.telemetry")

# How many recent samples to keep per route. 512 is roughly the last hour of a
# busy browsing session and a few kilobytes of floats — enough for a stable
# p95, small enough that the bound never has to be thought about again.
SAMPLES_PER_ROUTE = int(os.environ.get("TELEMETRY_SAMPLES", "512"))

# Distinct routes tracked. The API has a fixed handful, so this only binds the
# pathological case: a caller probing /api/<random> would otherwise mint a new
# bucket per request.
MAX_ROUTES = 64

# Anything slower than this is logged at WARNING rather than INFO. Set at the
# point where a user stops reading the loading sequence and starts wondering
# whether the page is broken.
SLOW_MS = float(os.environ.get("TELEMETRY_SLOW_MS", "3000"))


def _percentile(sorted_values: List[float], q: float) -> float:
    """Nearest-rank percentile.

    Nearest-rank rather than interpolated: with a few hundred samples the
    difference is noise, and every reported figure being a real measurement
    that actually happened is worth more here than smoothness.
    """
    if not sorted_values:
        return 0.0
    k = max(0, min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1)))))
    return sorted_values[k]


class Recorder:
    """Rolling latency and counters, safe across threads."""

    def __init__(self, samples: int = SAMPLES_PER_ROUTE, max_routes: int = MAX_ROUTES):
        self.samples = samples
        self.max_routes = max_routes
        self._lat: Dict[str, Deque[float]] = {}
        self._calls: Dict[str, int] = {}
        self._errors: Dict[str, int] = {}
        self._counters: Dict[str, int] = {}
        self._observed: Dict[str, Deque[float]] = {}
        self._started = time.time()
        self._lock = threading.Lock()

    def record(self, route: str, ms: float, status: int = 200) -> None:
        with self._lock:
            if route not in self._lat and len(self._lat) >= self.max_routes:
                # Drop the sample rather than the bound. Losing telemetry for
                # a route nobody meant to call is the cheap failure here.
                return
            self._lat.setdefault(route, deque(maxlen=self.samples)).append(ms)
            self._calls[route] = self._calls.get(route, 0) + 1
            if status >= 500:
                self._errors[route] = self._errors.get(route, 0) + 1

    def increment(self, name: str, by: int = 1) -> None:
        """Count something that is not a request — an export, a cache miss."""
        with self._lock:
            if name not in self._counters and len(self._counters) >= self.max_routes:
                return
            self._counters[name] = self._counters.get(name, 0) + by

    def observe(self, name: str, value: float) -> None:
        """Record a distribution that is not a duration — factors per query."""
        with self._lock:
            if name not in self._observed and len(self._observed) >= self.max_routes:
                return
            self._observed.setdefault(name, deque(maxlen=self.samples)).append(float(value))

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            routes = {}
            for route, values in self._lat.items():
                ordered = sorted(values)
                routes[route] = {
                    "calls": self._calls.get(route, 0),
                    "errors": self._errors.get(route, 0),
                    "sampled": len(ordered),
                    "p50_ms": round(_percentile(ordered, 0.50), 1),
                    "p95_ms": round(_percentile(ordered, 0.95), 1),
                    "p99_ms": round(_percentile(ordered, 0.99), 1),
                    "max_ms": round(ordered[-1], 1) if ordered else 0.0,
                }
            observed = {}
            for name, values in self._observed.items():
                ordered = sorted(values)
                observed[name] = {
                    "n": len(ordered),
                    "p50": round(_percentile(ordered, 0.50), 2),
                    "p95": round(_percentile(ordered, 0.95), 2),
                    "max": round(ordered[-1], 2) if ordered else 0.0,
                }
            return {
                "uptime_s": round(time.time() - self._started, 1),
                # Said in the payload, not only in the docs, because the number
                # most likely to be misquoted is the one read straight off an
                # endpoint by someone who never opened this file.
                "sampled_from": "one process — per-instance, not per-deployment",
                "window": f"last {self.samples} requests per route",
                "routes": routes,
                "counters": dict(self._counters),
                "observed": observed,
            }

    def reset(self) -> None:
        with self._lock:
            self._lat.clear()
            self._calls.clear()
            self._errors.clear()
            self._counters.clear()
            self._observed.clear()
            self._started = time.time()


RECORDER = Recorder()


def record(route: str, ms: float, status: int = 200) -> None:
    RECORDER.record(route, ms, status)


def increment(name: str, by: int = 1) -> None:
    RECORDER.increment(name, by)


def observe(name: str, value: float) -> None:
    RECORDER.observe(name, value)


def snapshot() -> Dict[str, Any]:
    return RECORDER.snapshot()


def install(app, recorder: Optional[Recorder] = None) -> None:
    """Time every `/api/*` request on a FastAPI app.

    Installed *after* the rate limiter, which in Starlette means it runs
    outside it — so a 429 is timed too. Rejections are part of what a client
    experiences, and a limiter that has started rejecting everything would
    otherwise show up as a sudden, flattering improvement in latency.
    """
    from fastapi import Request

    rec = recorder or RECORDER

    @app.middleware("http")
    async def _timing(request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            # Time the failure before re-raising. An exception path that is
            # slow and unmeasured is how a timeout hides.
            ms = (time.perf_counter() - t0) * 1000
            rec.record(path, ms, 500)
            _log(path, ms, 500, request.method)
            raise

        ms = (time.perf_counter() - t0) * 1000
        rec.record(path, ms, status)
        _log(path, ms, status, request.method)

        # Devtools plots Server-Timing on the network panel without any work
        # from us; X-Response-Time is what curl and load tests read.
        response.headers["Server-Timing"] = f"app;dur={ms:.1f}"
        response.headers["X-Response-Time"] = f"{ms:.1f}ms"
        return response


def _log(path: str, ms: float, status: int, method: str) -> None:
    """One structured line per request.

    JSON because the durable copy of this lives in a log aggregator, and
    because the alternative — a human-readable line that has to be re-parsed
    with a regex six months later to build a case study — is how "we have the
    numbers somewhere" becomes "we do not have the numbers".

    No client identifier, no geometry, no query text. This file exists to
    measure the service, and a latency log is a poor place to start keeping
    records of who asked what about which piece of land.
    """
    payload = json.dumps({
        "evt": "request",
        "route": path,
        "method": method,
        "status": status,
        "ms": round(ms, 1),
    })
    if ms >= SLOW_MS:
        log.warning(payload)
    else:
        log.info(payload)
