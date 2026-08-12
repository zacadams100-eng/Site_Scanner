# Product vision

Where this product is going, and — more usefully — what it must refuse in order
to get there.

Written during the autonomous transformation pass of 2026-08-12. It states an
ambition, and ambition is not evidence: nothing here is a commitment, a forecast
or a claim about traction. `docs/STATE_OF_PLAY.md` is what is actually true.

---

## The sentence

> Site Scanner becomes evidence infrastructure for land decisions — a
> standardised system that turns environmental, planning, infrastructure,
> heritage and specialist evidence into auditable intelligence for individual
> sites and portfolios.

---

## The competitor is not a product

It is **fragmented land due diligence**: GIS plus spreadsheets plus PDFs plus
consultant emails plus planning portals plus disconnected datasets. A
professional assembling a picture of a site today does it by hand, from sources
that do not agree on a format, and the person who receives the result cannot
tell what was checked from what was skipped.

Site Scanner is the layer that connects those worlds. It is explicitly **not**
trying to be a better ArcGIS: a GIS is a tool for making maps, and this is a
system for establishing what is known about a place and what is not.

---

## What it must never become

Each of these is a plausible product that would destroy the thing worth
building. They are listed because each will be suggested, by someone reasonable,
with a good argument.

- **A site score.** The single most requested feature and the one that would
  make this product actively harmful. A number that says "72" replaces the
  reasoning with a ranking, and the reasoning is the product. See
  `docs/EVIDENCE_STANDARD.md` principle 7 — enforced by tests that grep the
  served documents.
- **A map with AI commentary.** Generated prose over a map is confident, cheap
  and unfalsifiable. This product's value is that every sentence traces to a
  measurement.
- **A generic GIS clone.** The map is a means of drawing a site and reading a
  result. It is not the product.
- **A consultancy in software's clothing.** If the answer requires a person
  every time, it does not scale and it is not infrastructure.
- **A fake-data demo pretending to be production.** The single demonstration
  surface is labelled at every level, and a test enforces it on every path.

---

## The sequence

Each stage is only reachable once the one before it is real. Stated as
dependency, not as timeline.

**1. Excellent at one use case.** Land and evidence for English sites, for
environmental consultants, ecologists, land managers and the professionals who
commission their work. *Blocked on Earth Engine credentials — 28 of 271 factors
return real observations today.*

**2. The evidence record as the unit.** Every assessment recorded in a stable,
addressable, versioned form. **Implemented.** This is what makes everything
after it possible, and it is why it was built before anything needed it: a
longitudinal record can only be assembled from assessments that were recorded
comparably at the time.

**3. Portfolios.** From "tell me about this site" to "tell me about all of
these". *Aggregation implemented; storage and a UI are not.*

**4. Monitoring.** The same site, over time. The record makes it possible;
nothing consumes two records yet.

**5. Specialist scanners.** Heritage, geotechnical, arboricultural — first
party, then commissioned, then possibly third party. *Contract exercised by
three packages with no engine change; isolation and contract versioning are
missing.*

**6. Professional review.** Machine assessment co-signed by a named
professional. *Modelled; identity, authentication and the contractual meaning of
a co-sign are founder decisions.*

**7. The standard.** The form itself becomes the thing others adopt.

---

## Why the discipline is the asset

Every principle in the Evidence Standard is a constraint. Taken together they
are also the moat, and the reason is structural rather than moral:

A competitor can copy a scanner in a quarter. Copying the discipline requires
them to also give up the site score — which is what their sales team wants most,
what their demo looks best with, and what their first ten customers will ask
for. Most will not. The ones that do have built the same product, and the
market is better for it.

The compounding asset is the record. A structured, provenanced, versioned
account of what was observed about a place and when cannot be assembled
retroactively. Every month of records is a month a competitor starting today
cannot reproduce.

---

## Future verticals

Documented in `docs/FUTURE_VERTICALS.md`. The architecture is intended to carry
them; **none is implemented, and the document says so per vertical.** The
purpose of writing them down is to check that no decision taken today forecloses
one — not to imply they are coming.
