# Connecting the enquiry form

**Status: no receiver configured.** The form at `/request-a-site-scan` returns
**503** and tells the sender their message was not sent and not stored. That is
deliberate — see below — but it means the site currently cannot take an
enquiry, and this is the last thing standing between the marketing site and
being usable.

## Pick one. The first is quicker.

### Webhook — minutes

```bash
export ENQUIRY_WEBHOOK_URL="https://hooks.slack.com/services/..."
```

Anything that accepts a JSON POST works: a Slack incoming webhook, a Zapier
catch hook, a Make scenario, Formspree. The body is:

```json
{
  "source": "site-scanner/request-a-site-scan",
  "enquiry": { "name": "...", "email": "...", "organisation": "...",
               "site": "...", "detail": "...", "scanners": ["Land"] },
  "text": "a plain-text rendering of the same thing"
}
```

`text` is included so a Slack webhook shows something readable without anyone
writing a message template.

### SMTP — longer

All four are required; three of four counts as unconfigured, because a partial
configuration that reported itself as working would fail at send time *after*
telling the sender it succeeded.

```bash
export ENQUIRY_SMTP_HOST="smtp.example.com"
export ENQUIRY_SMTP_USER="postbox@example.com"
export ENQUIRY_SMTP_PASSWORD="..."
export ENQUIRY_TO="enquiries@example.com"
export ENQUIRY_SMTP_PORT=587          # optional, defaults to 587
export ENQUIRY_FROM="site@example.com" # optional, defaults to SMTP_USER
```

`Reply-To` is set to the enquirer, so replying goes to them rather than to the
mailbox the server authenticates as.

## On Vercel

Project → Settings → Environment Variables. The API runs as a Python function
(`api/index.py`), which mounts the same route, so no redeploy of the frontend
is needed — but the function does need a redeploy to pick up a new variable.

## Confirming it works

```bash
curl -s localhost:8000/api/enquiry/status
```

`{"configured": false}` → nothing will be delivered. `{"configured": true}` →
a receiver is set. The endpoint never says *which* receiver or any part of its
configuration.

Then send a real one through the form and check it arrives. A 200 with
`{"delivered": true, "via": "webhook"}` means a receiver accepted it.

## Why nothing is stored when there is no receiver

A submissions table sounds like the safe middle ground. It is not: it is
personal data at rest, in a database nobody is watching, with no retention
policy and nobody notified. Refusing the submission and saying so plainly is
both more honest to the sender and less of a liability than quietly
accumulating enquiries no one reads.

## Why a 503 rather than a thank-you page

The thank-you page says *"we have your enquiry"*. Showing it when nothing
received the submission is the same failure as a scanner reporting "clear" for
a check it could not run, and this codebase does not do that in either place.

The form instead shows the sender that the message was not sent, and warns them
to copy what they wrote before leaving the page.
