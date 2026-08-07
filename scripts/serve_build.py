#!/usr/bin/env python3
"""
Serve the production build exactly the way the deployment does.

Vercel's routing is declarative and lives in `vercel.json`, which means the
first time anyone finds out whether it is right is after a deploy. This
reproduces it locally — static files from `web/dist`, `/demo` to the demo page,
`/api/*` into the serverless function, everything else to `index.html` — so the
built bundle, the bundled basemap and the API can be exercised together before
a URL exists.

    python3 scripts/build_or_check.py     # (see DEPLOY.md for the build)
    npm --prefix web run build
    python3 scripts/serve_build.py        # http://127.0.0.1:8080

It is a verification tool, not a production server: single process, no
compression, no caching headers beyond the ones under test.
"""

import argparse
import json
import mimetypes
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "api"))


def build_app():
    if not DIST.exists():
        raise SystemExit("web/dist is missing — run: npm --prefix web run build")

    import index as fn                                  # api/index.py

    config = json.loads((ROOT / "vercel.json").read_text())
    headers = []
    for block in config.get("headers", []):
        if block["source"] == "/(.*)":
            headers = [(h["key"], h["value"]) for h in block["headers"]]

    async def app(scope, receive, send):
        if scope["type"] != "http":
            return
        path = scope["path"]

        # 1. The API, into the same function Vercel runs.
        if path.startswith("/api/"):
            await fn.app(scope, receive, send)
            return

        # 2. The self-contained demo.
        if path == "/demo":
            path = "/demo.html"

        # 3. Static files, then the SPA catch-all — the rewrite that turns a
        #    missing asset into a 200 of index.html. Reproduced faithfully
        #    because that behaviour has already cost this project one silently
        #    blank map; see DEPLOY.md, "Known gaps".
        target = DIST / path.lstrip("/")
        if not target.is_file():
            target = DIST / "index.html"

        body = target.read_bytes()
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        # Vercel serves text with an explicit charset; without it a file full
        # of em-dashes renders as mojibake and looks like an encoding bug in
        # the application.
        if ctype.startswith("text/") or ctype == "application/javascript":
            ctype += "; charset=utf-8"
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", ctype.encode())] +
                       [(k.lower().encode(), v.encode()) for k, v in headers],
        })
        await send({"type": "http.response.body", "body": body})

    return app


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    import uvicorn
    print(f"Serving the production build on http://127.0.0.1:{args.port}")
    uvicorn.run(build_app(), host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
