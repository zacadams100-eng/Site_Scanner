"""Header rules match the request path; rewrites change it afterwards.

The demo page is one large inline <script>, so it needs a CSP with
`script-src 'unsafe-inline'` where the rest of the site gets `script-src
'self'`. vercel.json had that relaxed rule keyed to `/demo.html`, and the
rewrite `/demo` -> `/demo.html` meant nobody ever requested that path.
Vercel evaluates headers against what the browser asked for, so a visitor to
/demo got the strict policy and the entire demo script was blocked.

The page still rendered — markup and styles are unaffected — so it looked
like a working site with an empty map rather than an error. Nothing appeared
in the deploy output, and the local file works because file:// carries no
CSP at all.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSP = "Content-Security-Policy"


def _config() -> dict:
    return json.loads((REPO_ROOT / "vercel.json").read_text())


def _csp_for(source: str) -> str | None:
    """The CSP the last matching header rule sets for an exact source path.

    Vercel applies every matching rule in order and later values win, which
    is what lets a specific path relax the site-wide policy.
    """
    found = None
    for rule in _config().get("headers", []):
        if rule.get("source") != source:
            continue
        for header in rule.get("headers", []):
            if header.get("key") == CSP:
                found = header.get("value")
    return found


def test_rewrites_do_not_lose_a_relaxed_csp():
    """If a destination has its own CSP, every source rewritten to it needs
    the same one — the destination path is never requested directly."""
    config = _config()
    mismatched = []
    for rewrite in config.get("rewrites", []):
        source, destination = rewrite.get("source"), rewrite.get("destination")
        if not source or not destination or destination.startswith("http"):
            continue
        dest_csp = _csp_for(destination)
        if dest_csp is None:
            continue
        if _csp_for(source) != dest_csp:
            mismatched.append(f"{source} -> {destination}")

    assert not mismatched, (
        "These rewrites send a request to a page with its own CSP, but the "
        "source path does not carry that CSP, so the browser gets the "
        "site-wide policy instead: " + ", ".join(sorted(mismatched))
    )


def test_demo_may_run_its_inline_script():
    """Stated directly, because this is the one that broke and the generic
    check above would pass if someone deleted both rules together."""
    for path in ("/demo", "/demo.html"):
        csp = _csp_for(path)
        assert csp is not None, f"{path} has no Content-Security-Policy rule"
        assert "script-src 'unsafe-inline'" in csp, (
            f"{path} does not permit inline script; the demo is a single "
            f"inline <script> and will render an empty page. Got: {csp}"
        )
