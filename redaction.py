"""
Strip credentials out of anything on its way to a log, a browser or CI.

Earth Engine puts the whole credentials dict into some of its exception
messages, so a bad key raises an error that *contains* the live private key.
That matters in three places here, and all three are reachable:

  * `routes_catalog` puts the exception text into the JSON the browser gets,
    so a failed query would serve the key to whoever drew the shape.
  * the check scripts print exceptions to stdout, and this repository is
    public, so CI logs are public.
  * anything that ends up in an issue, a PR comment or a pasted traceback.

The rule is that nothing formats an exception from the Earth Engine path
without going through `safe_message` first. Redacting at the point of display
rather than at the point of raising is deliberate: there is one place to get
right, and it stays right when a new caller appears.
"""

import re
from typing import Any

# Field names whose *values* are credentials. Google service account keys use
# all of these; the OAuth ones are here because the same helper covers the
# token refresh path.
SECRET_FIELDS = (
    "private_key",
    "private_key_id",
    "client_secret",
    "refresh_token",
    "access_token",
    "id_token",
    "client_id",
)

# "private_key": "-----BEGIN ...", including escaped quotes inside the value.
_FIELD_RE = re.compile(
    r"""(['"]?(?:%s)['"]?\s*[:=]\s*)(['"])(?:\\.|(?!\2).)*\2"""
    % "|".join(SECRET_FIELDS),
    re.IGNORECASE,
)

# A PEM block that arrived without a field name around it — a bare traceback,
# or a key pasted into a message. Matches both real newlines and the escaped
# \n that a JSON-encoded key carries.
_PEM_RE = re.compile(
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
    re.DOTALL,
)

# Bearer tokens in an Authorization header echoed back in an error.
_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]{16,}=*", re.IGNORECASE)

REDACTED = "[redacted]"


def redact(text: str) -> str:
    """Replace credential material in `text` with a marker."""
    if not text:
        return text
    text = _PEM_RE.sub(REDACTED, text)
    text = _FIELD_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}{m.group(2)}", text)
    text = _BEARER_RE.sub(lambda m: m.group(1) + REDACTED, text)
    return text


def safe_message(exc: BaseException, limit: int = 400) -> str:
    """A single line describing `exc`, with credentials stripped.

    Truncated because Earth Engine errors can run to thousands of characters
    of serialised request — which is both useless to a user and the part most
    likely to be carrying something sensitive.
    """
    message = redact(f"{type(exc).__name__}: {exc}")
    message = " ".join(message.split())
    if len(message) > limit:
        message = message[:limit - 1].rstrip() + "…"
    return message


def safe_str(value: Any, limit: int = 400) -> str:
    """`safe_message` for things that are not exceptions."""
    text = " ".join(redact(str(value)).split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"
