"""
The API as a Vercel serverless function.

Why this exists: until now the only deployment path put the frontend on Vercel
and the API on Cloud Run, which meant a public URL required a Google Cloud
account, a billing profile and an Earth Engine service account before anyone
could see anything at all. That is a lot of setup to stand between a repository
and a link you can send someone.

This runs the credential-free backend — the same `routes_catalog` router the
real one mounts, so the API contract is identical — inside Vercel's Python
runtime. Deploying becomes: connect the repo, press deploy. No secrets, no
second service, no Earth Engine.

What you get on that URL: the whole interface, the full catalogue, the map, the
templates, markers and every export. Factors return generated data and say so,
exactly as the local mock does, plus whatever open-data sources reach the
network (see `open_data.py`) — those are real.

What you do not get: Earth Engine factors. Those need `app.py`, credentials and
a container; see DEPLOY.md §1. The two are meant to coexist — point the
frontend at Cloud Run by setting the API rewrite in vercel.json when the real
backend is up.
"""

import os
import pathlib
import sys

# The project modules live at the repository root, one level up. Vercel bundles
# them via the `includeFiles` glob in vercel.json.
ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("CONTOUR_CACHE_TTL", "900")

from mock_ee_backend import app as _app          # noqa: E402

# Open-data sources are registered here once `open_data.py` lands; see
# DEPLOY.md. Everything not registered returns generated data and says so.
try:
    import open_data                              # noqa: E402
    import routes_catalog                         # noqa: E402
    open_data.install(routes_catalog.REAL_SERIES)
except ImportError:
    pass


def _normalise_path(scope: dict) -> dict:
    """Put the request back on the path FastAPI expects.

    Vercel routes a request to this function in one of several ways depending
    on the rewrite that matched, and not all of them preserve `/api/catalog` as
    the ASGI path — some deliver `/api/index`, some deliver `/`, and the real
    path arrives in a header instead. Rather than depend on which, this reads
    the original path from whichever source has it.

    Doing it here, in one place, is what stops the deployment failing with a
    404 that looks like a routing bug in the application.
    """
    path = scope.get("path", "/")
    headers = {k.decode().lower(): v.decode()
               for k, v in scope.get("headers", [])}

    original = (headers.get("x-vercel-original-path")
                or headers.get("x-forwarded-uri")
                or headers.get("x-original-uri"))
    if original:
        path = original.split("?", 1)[0]
    elif path.startswith("/api/index"):
        # The function's own name is not a route we serve. `/api/index/catalog`
        # means `/api/catalog`; a bare `/api/index` is the health check.
        rest = path[len("/api/index"):]
        path = f"/api{rest}" if rest.startswith("/") and rest != "/" else "/"

    scope = dict(scope)
    scope["path"] = path
    scope["raw_path"] = path.encode()
    return scope


class PathNormalising:
    """Thin ASGI wrapper. Deliberately not middleware on the FastAPI app: the
    path has to be right *before* routing, not after."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            scope = _normalise_path(scope)
        await self.inner(scope, receive, send)


app = PathNormalising(_app)
