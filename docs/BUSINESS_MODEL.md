# Business model architecture

**Nothing here is implemented.** There is no payment system, no pricing, no
metering, no accounts. This document records how the *product* is shaped around
two packages, so that the shape does not have to be retrofitted later.

Pricing numbers are deliberately absent. They depend on customer conversations
that have not happened, and a number written here would be quoted back as if it
had been decided.

---

## The two packages the product is built around

### Rule it out

**Fast evidence scan.** Draw a site, run a scanner, see what needs attention.
The answer a professional wants in the first ten minutes: is there anything here
that changes whether I proceed?

Already the product's default path. Its output is the radar and the findings.
The word *rule out* is load-bearing and it is honest: a clear result rules a
question **out of the fast lane**, not out of existence — which is exactly the
distinction the evidence model already enforces.

### Full brief

**Deep evidence, investigations, professional follow-up, auditable record.** The
document that leaves the building and is read by someone who was not there.

`/api/brief` produces it today. What separates it from the fast scan is not more
data but a different artefact: the full assessment log, every attribution, the
gaps stated, the investigation chain traceable in both directions.

### Portfolio, later

Many sites, monitored over time. Aggregation is implemented; storage, a UI and a
job queue are not.

---

## Why the packages fall out of the architecture

They were not designed as tiers and then implemented. They are two real
artefacts the product already produces — a radar and a record — and they map
onto two genuinely different questions. That is worth noting because the usual
failure of a tiered product is withholding something arbitrary to create a
boundary. Here the boundary already exists.

The one thing that must never be a paid tier: **the gaps.** "What could not be
assessed" cannot sit behind an upgrade, because a free scan that showed findings
without gaps would be the exact misreading this product exists to prevent, sold.

---

## Revenue possibilities

Recorded as strategic architecture. None is assumed; several are mutually
exclusive.

| | Model | Depends on |
| --- | --- | --- |
| 1 | Individual scans | Nothing new |
| 2 | Professional reports | Nothing new |
| 3 | Portfolio subscription | Storage, accounts, job queue |
| 4 | Enterprise licence | The above, plus tenancy and support |
| 5 | Specialist scanner revenue share | Contributor identity, isolation, contract versioning |
| 6 | Review / co-sign fees | Reviewer identity, verification, contractual meaning of a co-sign |
| 7 | API / data access | Rate limiting (exists), auth, licence review of onward supply |
| 8 | Certification against the standard | The standard being adopted by anyone else first |
| 9 | Monitoring subscription | Storage plus change detection |

The dependency column is the useful part. **1 and 2 need nothing that does not
exist**; everything else is gated on storage, identity, or an external decision.

Item 7 carries a hazard the others do not: several sources here are licensed for
use, not for onward supply. Any data-access product needs
`DATA_LICENSING.md` re-read per source first, and two licence questions are
already open.

---

## What the product must not do to make money

- Charge for the gaps.
- Sell a score, or a "premium" ranking.
- Present a review as having happened because a tier includes it.
- List a third-party scanner in a way that implies verification nobody did.
- Sell onward access to data licensed only for use.

Each of these would work commercially for a while. Each would end the thing that
makes the product worth more than a spreadsheet.
