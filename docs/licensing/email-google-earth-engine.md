# Draft: Google Earth Engine — commercial use enquiry

**Status:** draft, not sent. Fill the four bracketed fields and send.
**To:** the Earth Engine commercial team — the contact form at
<https://earthengine.google.com/commercial/> routes here; there is no public
mailbox, so send it through the form and keep a copy of this text.
**Subject:** Commercial licensing — batch derivation with no end-user Earth Engine access

---

Hello,

I am building **Site Scanner**, a web application that shows how a piece of
land in England has changed over time. A user draws a boundary on a map, picks
from a catalogue of environmental and land-use indicators, and gets a monthly
time series and a report for that area. The intended users are property
developers, planning consultants, agricultural advisers and insurers — so this
would be a commercial product, not a research or teaching tool.

Our Earth Engine account is currently registered for non-commercial use. I
want to establish the correct licence before, not after, we take money for
this, and I have a specific architectural question that determines which
licence we need.

**What we do with Earth Engine today.** Users' requests reach Earth Engine
directly. A drawn polygon becomes a `reduceRegion` over Sentinel-2, ERA5-Land,
MODIS LST and ESA WorldCover, once per month in the requested window. This is
the model I assume needs a full commercial licence, and it is also poor
engineering — latency and quota sit on the user's request path.

**What we intend to move to.** Earth Engine used only as a batch derivation
engine, never on the user path:

1. A scheduled job computes derived products — monthly NDVI and the other
   indices, aggregated to a fixed spatial grid over England — and exports them
   to our own storage.
2. The application serves users entirely from that storage. No end user ever
   holds an Earth Engine credential, issues an Earth Engine query, or receives
   Earth Engine imagery. What they receive is aggregated statistics over a
   grid: a number per cell per month, not pixels.

**My questions:**

1. Does the second model require a commercial Earth Engine licence, or does
   the batch-derivation-then-serve pattern fall under different terms? I have
   read the Earth Engine Terms of Service and I do not think it answers this
   cleanly, which is why I am asking rather than assuming.
2. If a commercial licence is required for the second model, what does it
   cost at our scale? Our processing footprint is small and predictable:
   England only (roughly 130,000 km²), monthly composites, about a dozen
   derived indices, backfilled once over 2010–present and then incremental
   from that point.
3. Is there an intermediate tier for a pre-revenue product? We would rather
   pay for the correct licence now than build on the wrong one and be
   re-architecting under commercial pressure later.
4. Are there restrictions on **redistributing the derived products** — for
   example, letting a customer export a CSV of monthly NDVI values for their
   own site — that are separate from the Earth Engine licence itself and come
   from the underlying dataset providers?

I am happy to describe the pipeline in more detail or to have a call.

Thank you,

[NAME]
[COMPANY, or "sole trader" if that is the honest answer]
[EMAIL]
[The Earth Engine project ID and the email the account is registered to]

---

## Notes for whoever sends this

- **Do not soften question 1.** The whole point is a clear answer on the
  batch-derivation pattern. A vague reply is worse than a "yes, commercial",
  because it leaves the architecture undecidable.
- **Send it before the first paying customer, not before launch.** A free
  public demo is arguably still non-commercial; taking money is not.
- **Do not offer to remove the Earth Engine dependency in the email.** Keep
  the Copernicus option (the other draft in this folder) as your own leverage
  and your own fallback, not as a negotiating position offered up front.
- Record the reply and its date in `DECISION-LOG.md` in this folder, including
  a "no reply after N weeks" outcome — silence is an answer here and it means
  Path C.
