# Business facts still needed

Every item below has a **built, working component and an honest empty state**.
Nothing is broken and nothing is a placeholder pretending to be real — the
pages say plainly that the fact does not exist yet. Verified in a browser at
1440×900 and 390×844: no lorem, no invented names, no example.com, no "TBC",
no broken layouts.

**Do not fill any of these in without the real value.** A fabricated address or
an invented case study is the one kind of dishonesty a marketing site makes
easy, and it undermines a product whose entire argument is that it does not
claim what it cannot show.

Ordered by what blocks a launch.

---

## 1. Where enquiries go — **blocks launch**

**Needed:** a monitored destination for the contact form.

The cheapest is a webhook URL — Slack, Zapier, Make, Formspree all work.
One environment variable: `ENQUIRY_WEBHOOK_URL`. Alternatively SMTP
credentials and a mailbox. See `docs/ENQUIRY_SETUP.md`.

**Until then:** the form returns 503 and tells the sender their message was not
sent and not stored. That is honest, and it means the site cannot take an
enquiry.

## 2. A monitored email address

**Needed:** one address, for `/contact` → "Other enquiries".

**Current state:** *"Contact details are not published yet. A monitored email
address goes here."*

**Where it goes:** `web/src/site/Pages.tsx`, the `Contact` component.

## 3. Canonical domain

**Needed:** the production URL, as `VITE_SITE_ORIGIN`.

**Unblocks three things at once:** canonical tags, `og:url`, and `sitemap.xml`
— all three are omitted entirely rather than pointed at a guess, because a
wrong canonical tells search engines the real page is elsewhere and a wrong
`og:url` is cached by every platform that reads it.

```bash
VITE_SITE_ORIGIN=https://the-real-domain.example
```

Also uncomment the `Sitemap:` line in `web/public/robots.txt` with the same
origin.

## 4. Legal entity

**Needed for `/privacy`:** company name, registered address, data-protection
contact, retention period — and a legal review of the whole page.

**Current state:** the policy describes what the site actually does (no
analytics configured, no cookies set, form data used only to reply) and does
not invent a controller.

**Note:** now that the enquiry form delivers somewhere, the privacy policy must
say where enquiry data goes and how long it is kept, before the form is turned
on for the public.

## 5. Team

**Needed for `/about`:** names, roles, short bios, photography.

**Current state:** the section is present and says no team is published.
**No placeholder people.**

## 6. Case studies

**Needed:** real projects — site, scanner used, what was established, what was
not, what it prompted.

**Current state:** *"We would rather show nothing than an illustration
presented as a client."*

## 7. Response-time commitment

**Needed:** an SLA, if there is one.

**Current state:** `/thank-you` says *"We will review it and get back to you"*
with no timeframe. Inventing "within one business day" would be a commitment
nobody made.

## 8. Analytics — a decision, not a fact

**Needed:** whether to track at all. If yes, `VITE_GA_MEASUREMENT_ID` plus a
consent mechanism.

**Current state:** `lib/analytics.ts` is env-configured, consent-gated and
inert. Nothing is collected.

---

## Not blocked on business facts

For completeness — these are open but are engineering or supply, not decisions:

- **Earth Engine credentials** — `docs/EE_SETUP.md`. Blocks real findings and
  all six product screenshots.
- **21 unsupplied image slots** — `web/public/assets/README.md` has the ordered
  checklist.
- **Coastal's two thresholds** need a coastal engineer's sign-off. They are
  labelled unvalidated in the UI and the docs; see
  `docs/SCANNER_SPECIFICATION.md`.
