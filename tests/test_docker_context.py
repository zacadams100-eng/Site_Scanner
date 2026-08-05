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


def test_vercelignore_excludes_every_python_module():
    """The frontend deploy carries no Python, and drifts the same way.

    This lives beside the Dockerfile check because it is the same failure:
    a hand-maintained list of modules that nobody updates when a module is
    added. `.vercelignore` had fallen two behind — `ee_series` and
    `redaction` were being uploaded to Vercel.

    The consequence is milder than the Dockerfile's (Vercel ignores the
    stray files rather than crashing), but excluding `requirements.txt` is
    what stops Vercel's framework detection deciding this is a Python
    project, and a half-excluded backend muddies that signal.
    """
    ignored = {
        line.strip()[: -len(".py")]
        for line in (REPO_ROOT / ".vercelignore").read_text().splitlines()
        if line.strip().endswith(".py") and not line.strip().startswith("#")
    }
    leaked = _root_modules() - ignored
    assert not leaked, (
        ".vercelignore does not exclude: "
        + ", ".join(sorted(f"{m}.py" for m in leaked))
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
