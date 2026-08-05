"""The Dockerfile copies modules by name; this checks the list is complete.

`COPY . .` is deliberately not used — the repo is public and a stray service
account key in the working tree would otherwise be baked into a pushed image.
The cost of that choice is a hand-maintained list, and a hand-maintained list
drifts. By the time the first deploy was attempted this one was five modules
behind: `routes_catalog`, `catalog`, `series`, `cache` and `geometry` had all
been added to the import graph and none had been added to the Dockerfile.

That failure mode is unusually quiet from the outside. The missing module is
absent from the image rather than broken in it, so `import` raises during
startup and Cloud Run reports a failed revision with no application logs —
which looks exactly like the credentials problem DEPLOY.md tells you to check
first. Better to fail here, in a test that needs no cloud account.
"""

import ast
import re
import subprocess
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# What the container actually serves. APP_MODULE selects between them at
# runtime, so both have to be present in the image.
ENTRY_POINTS = ("app", "mock_ee_backend")


def _root_modules() -> set:
    return {p.stem for p in REPO_ROOT.glob("*.py")}


def _local_imports(module: str, known: set) -> set:
    """Names imported by `module` that resolve to a module at the repo root.

    Reads the source rather than importing it: importing `app` would run
    `init_earth_engine()` and need credentials, which is the whole reason this
    test can run without any.
    """
    tree = ast.parse((REPO_ROOT / f"{module}.py").read_text())
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")[0]
                if head in known:
                    found.add(head)
        elif isinstance(node, ast.ImportFrom):
            # `level > 0` is a relative import; there are no packages here.
            if node.level == 0 and node.module:
                head = node.module.split(".")[0]
                if head in known:
                    found.add(head)
    return found


def _reachable_modules() -> set:
    """Every root module reachable from an entry point, transitively.

    Function-local imports count: `routes_catalog` pulls geometry helpers from
    `mock_ee_backend` inside a function body, so the real backend needs the
    mock present even though it never serves it.
    """
    known = _root_modules()
    seen = set()
    queue = list(ENTRY_POINTS)
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        queue.extend(_local_imports(module, known) - seen)
    return seen


def _copied_modules() -> set:
    """Python module names the Dockerfile copies into the image."""
    text = (REPO_ROOT / "Dockerfile").read_text()
    # Join backslash continuations so a multi-line COPY reads as one.
    text = re.sub(r"\\\n\s*", " ", text)
    copied = set()
    for line in text.splitlines():
        if not line.strip().startswith("COPY "):
            continue
        for token in line.split()[1:]:
            if token.endswith(".py"):
                copied.add(token[: -len(".py")])
    return copied


def test_dockerfile_copies_every_module_the_app_imports():
    missing = _reachable_modules() - _copied_modules()
    assert not missing, (
        "Dockerfile does not COPY: "
        + ", ".join(sorted(f"{m}.py" for m in missing))
        + ". The container will crash on startup with ModuleNotFoundError."
    )


def _vercel_ignored_modules() -> set:
    return {
        line.strip()[: -len(".py")]
        for line in (REPO_ROOT / ".vercelignore").read_text().splitlines()
        if line.strip().endswith(".py") and not line.strip().startswith("#")
    }


def test_vercel_uploads_what_the_serverless_function_imports():
    """api/index.py serves the mock backend from Vercel, so its imports have
    to survive .vercelignore.

    Same failure mode as the Dockerfile's, with the same cause and a worse
    symptom: the function bundles fine and 500s on first request instead of
    failing at deploy time.
    """
    known = _root_modules()
    seen, queue = set(), ["mock_ee_backend"]
    while queue:
        module = queue.pop()
        if module in seen:
            continue
        seen.add(module)
        queue.extend(_local_imports(module, known) - seen)

    excluded = seen & _vercel_ignored_modules()
    assert not excluded, (
        ".vercelignore excludes modules the serverless function imports: "
        + ", ".join(sorted(f"{m}.py" for m in excluded))
    )


def test_vercel_does_not_upload_the_earth_engine_backend():
    """`app.py` and `ee_series.py` import `ee`, and api/requirements.txt does
    not install earthengine-api. Uploading them would put code in the bundle
    that cannot import, for a path the function never serves."""
    ignored = _vercel_ignored_modules()
    for module in ("app", "ee_series"):
        assert module in ignored, (
            f"{module}.py imports earthengine-api and must stay out of the "
            "Vercel bundle"
        )


# Everything Vercel needs in order to build the frontend. If any of these is
# excluded, the build fails on their machine and nowhere else — a local build
# reads the working tree and never consults .vercelignore at all.
FRONTEND_BUILD_INPUTS = (
    "web/package.json",
    "web/package-lock.json",
    "web/index.html",
    "web/vite.config.ts",
    "web/tsconfig.json",
    "web/src/App.tsx",
    "web/public/favicon.svg",
    # The one that actually broke. `prebuild` runs it, and MapLibre renders a
    # blank map without the worker files it copies.
    "web/scripts/copy-maplibre-worker.mjs",
    # Copied to web/public/demo.html by vercel.json's buildCommand.
    "demo/site-scanner-demo.html",
)


def test_vercelignore_keeps_what_the_build_needs():
    """.vercelignore uses .gitignore syntax, so bare directory names match at
    any depth: `scripts/` excluded web/scripts/ as well as the root one, and
    the first real deploy failed with MODULE_NOT_FOUND in seven seconds.

    Rather than reimplement gitignore matching and get it subtly wrong, this
    hands the patterns to git itself — the same matcher Vercel's rules follow.
    """
    ignore_text = (REPO_ROOT / ".vercelignore").read_text()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / ".gitignore").write_text(ignore_text)
        for rel in FRONTEND_BUILD_INPUTS:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()

        # check-ignore exits 0 and echoes the paths it would ignore.
        result = subprocess.run(
            ["git", "check-ignore", *FRONTEND_BUILD_INPUTS],
            cwd=root,
            capture_output=True,
            text=True,
        )
        excluded = [line for line in result.stdout.splitlines() if line.strip()]

    assert not excluded, (
        ".vercelignore excludes files the Vercel build needs: "
        + ", ".join(sorted(excluded))
    )


def test_dockerfile_copies_nothing_that_is_not_imported():
    """A stale name is a smaller problem than a missing one, but it still
    misleads: it implies the module is part of the served app when it is not,
    and a rename would leave a COPY that fails the build for no reason."""
    unused = _copied_modules() - _reachable_modules()
    assert not unused, (
        "Dockerfile copies modules nothing imports: "
        + ", ".join(sorted(f"{m}.py" for m in unused))
    )
