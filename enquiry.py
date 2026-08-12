"""
Delivering an enquiry to a human.

The form on `/request-a-site-scan` validated and discarded for as long as it
has existed. This is the receiver.

## The rule this module exists to enforce

**A form that cannot deliver must not say it did.** Every path below returns a
status the caller has to handle, and the "no receiver configured" case is a
first-class outcome rather than a swallowed exception. The frontend shows a
different screen for it, because telling someone "we have your enquiry" when
nothing received it is the same class of dishonesty as inventing a finding.

## Two receivers, both optional, cheapest first

`ENQUIRY_WEBHOOK_URL` is a POST of the enquiry as JSON. It is first because it
is the cheapest thing to stand up: a Slack incoming webhook, a Zapier catch
hook, a Formspree endpoint or a Make scenario all accept exactly this and need
no mail server, no DNS records and no deliverability reputation.

SMTP is there for a deployment that would rather own the mail path. It needs
four variables and a host that will relay for you, which is more setup than
most people want on day one.

If neither is configured the enquiry is **not stored**. A submissions table
sounds like the safe middle ground and is not: it is personal data at rest, in
a database nobody is watching, with no retention policy and no one notified.
Refusing the submission and saying so is both more honest and less of a
liability than silently accumulating enquiries nobody reads.
"""

from __future__ import annotations

import json
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass, asdict
from email.message import EmailMessage
from typing import Any, Dict, Optional, Tuple

log = logging.getLogger("site_scanner.enquiry")

#: How long to wait on a receiver before giving up. Short: a person is watching
#: a spinner, and a webhook that takes longer than this is not going to answer.
TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class Enquiry:
    """One submission. Deliberately small.

    No tracking fields, no fingerprint, no IP. The privacy policy says this
    form's data is used to reply to the enquiry, and collecting anything beyond
    what a reply needs would make that statement false.
    """

    name: str
    email: str
    organisation: str
    site: str
    detail: str
    scanners: Tuple[str, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["scanners"] = list(self.scanners)
        return d

    def as_text(self) -> str:
        lines = [
            f"Name:         {self.name}",
            f"Email:        {self.email}",
            f"Organisation: {self.organisation or '—'}",
            f"Site:         {self.site or '—'}",
            f"Scanners:     {', '.join(self.scanners) or '—'}",
            "",
            self.detail,
        ]
        return "\n".join(lines)


class NotConfigured(RuntimeError):
    """No receiver is configured, so nothing can be delivered.

    Its own type rather than a bool return, so a caller cannot accidentally
    treat "nowhere to send it" as success by ignoring a flag.
    """


def configured_receiver() -> Optional[str]:
    """Which receiver would handle an enquiry, or `None`.

    Read at call time rather than import time so a deployment can set the
    variable without a rebuild, and so a test can change it.
    """
    if os.environ.get("ENQUIRY_WEBHOOK_URL"):
        return "webhook"
    if all(os.environ.get(k) for k in
           ("ENQUIRY_SMTP_HOST", "ENQUIRY_SMTP_USER",
            "ENQUIRY_SMTP_PASSWORD", "ENQUIRY_TO")):
        return "smtp"
    return None


def _deliver_webhook(enquiry: Enquiry) -> None:
    import urllib.request

    url = os.environ["ENQUIRY_WEBHOOK_URL"]
    payload = json.dumps({
        "source": "site-scanner/request-a-site-scan",
        "enquiry": enquiry.as_dict(),
        # A plain-text rendering as well as the fields, so a Slack webhook
        # shows something readable without anyone writing a template.
        "text": enquiry.as_text(),
    }).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        if response.status >= 300:
            raise RuntimeError(f"webhook returned {response.status}")


def _deliver_smtp(enquiry: Enquiry) -> None:
    message = EmailMessage()
    message["Subject"] = f"Site scan enquiry — {enquiry.name}"
    message["From"] = os.environ.get("ENQUIRY_FROM") or os.environ["ENQUIRY_SMTP_USER"]
    message["To"] = os.environ["ENQUIRY_TO"]
    # So a reply goes to the person who wrote in rather than to the mailbox
    # the server authenticates as.
    message["Reply-To"] = enquiry.email
    message.set_content(enquiry.as_text())

    host = os.environ["ENQUIRY_SMTP_HOST"]
    port = int(os.environ.get("ENQUIRY_SMTP_PORT", "587"))
    with smtplib.SMTP(host, port, timeout=TIMEOUT_SECONDS) as server:
        server.starttls(context=ssl.create_default_context())
        server.login(os.environ["ENQUIRY_SMTP_USER"],
                     os.environ["ENQUIRY_SMTP_PASSWORD"])
        server.send_message(message)


def deliver(enquiry: Enquiry) -> str:
    """Send it. Returns the receiver that took it.

    Raises `NotConfigured` when there is nowhere to send it, and lets any
    delivery failure propagate — both are things the caller must tell the user
    about rather than absorb.
    """
    receiver = configured_receiver()
    if receiver is None:
        # Loud, because the alternative is discovering months later that the
        # contact form was never connected on this deployment.
        log.error(
            "ENQUIRY NOT DELIVERED — no receiver configured. Set "
            "ENQUIRY_WEBHOOK_URL, or the ENQUIRY_SMTP_* variables. "
            "The submission was refused and NOT stored. See docs/ENQUIRY_SETUP.md."
        )
        raise NotConfigured("no enquiry receiver is configured")

    if receiver == "webhook":
        _deliver_webhook(enquiry)
    else:
        _deliver_smtp(enquiry)
    # The enquiry's own content is never logged: it is personal data, and a
    # log line is the easiest place to leak it from.
    log.info("enquiry delivered via %s", receiver)
    return receiver
