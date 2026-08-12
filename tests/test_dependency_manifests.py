"""Every third-party feature the code uses must be declared where it is installed.

The failure this catches is the quietest kind there is. `pydantic.EmailStr` is
an ordinary import from an already-declared package, so nothing about
`from pydantic import EmailStr` looks like a new dependency. It is one: pydantic
defers email syntax checking to `email-validator`, and raises only when the
model class is *built* — at import time, from module scope.

So a manifest missing it produces:

    ImportError: email-validator is not installed, run `pip install pydantic[email]`

raised while `routes_enquiry` is being imported, which both `app.py` and
`mock_ee_backend.py` do at module scope. The container never starts and the
serverless function 500s on every route, not just the enquiry one — a missing
dependency in a leaf module takes down the whole API because the import is
eager.

It was missing from `requirements.txt` and `api/requirements.txt` both, and the
suite did not catch it because the developer environment had it installed
transitively. That is the general shape: **a test environment that happens to
have a package proves nothing about the manifest that ships.** This file tests
the manifests as text rather than testing the imports, because the imports pass
here for reasons that do not travel.

`tests/test_docker_context.py` is the sibling of this file and covers the other
half — which *local* modules reach the image. This one covers which
*third-party* distributions reach the environment.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The manifests that install the Python runtime, and what each one serves.
#:
#: `api/requirements.txt` is deliberately not the root one — it omits
#: earthengine-api and its Google client stack, which would blow past the
#: serverless bundle limit. That divergence is the reason a dependency can be
#: correct in one and missing in the other, which is exactly what happened.
MANIFESTS = {
    "requirements.txt": "the container (app.py and mock_ee_backend.py)",
    "api/requirements.txt": "the Vercel serverless function",
}

#: Features that need a distribution beyond the one they are imported from.
#:
#: Keyed by the source pattern that reveals the need, valued by the
#: distribution that must be declared. Deliberately a small explicit table
#: rather than a general dependency resolver: the general version would need to
#: model extras, markers and transitive graphs, and would be a second package
#: manager with its own bugs. Three entries that are true beat a resolver that
#: is approximately right.
HIDDEN_DEPENDENCIES = {
    # pydantic defers RFC 5322 validation. Raised at class-construction time,
    # which is import time, which is why it takes the whole app down.
    r"\bEmailStr\b": "email-validator",
}


def _declared(manifest: str) -> set:
    """Distribution names declared in a manifest, normalised.

    PEP 503 treats `-`, `_` and `.` as equivalent and comparison as
    case-insensitive, so `Email_Validator` and `email-validator` are one name.
    Matching on the raw string would let a correct manifest fail this test.
    """
    text = (REPO_ROOT / manifest).read_text(encoding="utf-8")
    names = set()
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        # Strip version specifiers and extras: `uvicorn[standard]==0.30.6`.
        name = re.split(r"[<>=!~\[;]", line)[0].strip()
        if name:
            names.add(re.sub(r"[-_.]+", "-", name).lower())
    return names


def _bundled_sources(manifest: str) -> list:
    """The Python files the manifest's environment actually imports.

    Both environments import `routes_enquiry` through their entry point, so
    for the dependencies this table covers the set is the same. It is computed
    per manifest rather than shared so that a future divergence — a module the
    container has and the function does not — is expressible rather than
    silently wrong.
    """
    if manifest == "api/requirements.txt":
        # .vercelignore keeps app.py and ee_series.py out of the bundle; the
        # function serves mock_ee_backend and what it imports.
        skip = {"app.py", "ee_series.py"}
    else:
        skip = set()
    return [p for p in REPO_ROOT.glob("*.py") if p.name not in skip]


@pytest.mark.parametrize("manifest", sorted(MANIFESTS))
def test_hidden_dependencies_are_declared(manifest):
    """A feature whose distribution is not its import name must still be pinned.

    Failure message names the file and the line, because the fix is one line in
    a manifest and the useful part is knowing which manifest.
    """
    declared = _declared(manifest)
    for pattern, distribution in HIDDEN_DEPENDENCIES.items():
        users = [
            p.name for p in _bundled_sources(manifest)
            if re.search(pattern, p.read_text(encoding="utf-8"))
        ]
        if not users:
            continue
        assert re.sub(r"[-_.]+", "-", distribution).lower() in declared, (
            f"{manifest} serves {MANIFESTS[manifest]} and bundles "
            f"{', '.join(sorted(users))}, which need {distribution!r}. "
            f"It is not declared, so that environment raises ImportError "
            f"during startup and every route fails, not only the one that "
            f"uses the feature."
        )


@pytest.mark.parametrize("manifest", sorted(MANIFESTS))
def test_every_dependency_is_pinned(manifest):
    """An unpinned dependency makes the deployed environment unreproducible.

    Both manifests already pin everything. Asserting it keeps a `requests`
    added in a hurry from silently floating, which is how a working deploy
    starts failing with no commit that explains it.
    """
    text = (REPO_ROOT / manifest).read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        assert "==" in line, (
            f"{manifest}: {line!r} is not pinned. The deployed environment "
            f"then depends on the date it was built."
        )
