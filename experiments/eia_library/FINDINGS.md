# Findings — shared EIA library (item 11)

Run it yourself: `python3 -m experiments.eia_library.report`

**Short version: the feature as described cannot be made safe, and a narrower
version of it can. The narrowing is not a compromise on quality — it is a
different product claim, and worth making deliberately rather than discovering
after launch.**

---

## Test A — stripping identifiers from EIA text

| | Leaked | Findings retained |
| --- | ---: | ---: |
| Dev passages (redactor written against these) | 7.1% | 100% |
| **Held-out passages** | **30.8%** | **100%** |

Nearly a third of identifiers survive on text the redactor was not built
against. What survives is not a random third:

- `Guildford`, `Effingham` — bare settlement names. No pattern distinguishes a
  town from any other capitalised word. Needs a gazetteer (OS Open Names has
  around 870,000 UK entries and is free).
- `BHSE`, `Bloor's` — the client returning as an acronym and as a possessive,
  after the full company name was correctly removed from the header. **No
  pattern can catch these**, because knowing that `BHSE` is a client requires
  knowing who the client is.

That second class is the important one. It is not a gap in the rules; it is
outside what rules can do.

### The thing that took two attempts, and generalises

Twice, the mechanism protecting the *valuable* content punched a hole in the
redaction:

1. Species binomials were protected by shape — capitalised word, then lowercase
   word. That matched `Homes ownership` and `Hartley and`, and because a
   protected span blocks every redaction rule, the false species match shielded
   `Bloor Homes` and `J. Hartley` behind it.
2. The fix used Latin epithet endings, including `-e`, `-a`, `-is`. Those are
   also the endings of an enormous share of ordinary English, so `Road
   frontage` parsed as a species and shielded the site name.

Both were caught only by measuring. Both look correct while reading the code.

The general form is worth writing down, because it will recur in any attempt at
this: **the protection mechanism and the redaction mechanism are adversaries.**
Every exception carved out to save the ecology is a doorway an identifier walks
through, and the two cannot be tuned independently.

The final retention of 100% is real but should not be read as comfort — it was
bought by anchoring person-matching on a list of given names, and a name outside
that list is simply not detected. Safety and value trade against each other here
along one axis, and this configuration sits at the value end.

---

## Test B — the geometry, which is the harder problem

Even with the text perfectly clean, the boundary identifies the site. A red-line
application boundary is public, so matching a published shape back to its
application is a spatial join, not an attack.

**Fuzzing the coordinates does not work:**

| Rounding | Precision | Still matched to its own original |
| ---: | ---: | ---: |
| 5 dp | ~1 m | **100.0%** |
| 4 dp | ~11 m | 83.8% |
| 3 dp | ~111 m | 8.5% |

Fuzzing only anonymises at ~111 m — and a 0.3 ha parcel is about 60 m across, so
by then there is no boundary left to publish. **The fuzzing that works and the
fuzzing that preserves the data do not overlap.**

**Generalising to a cell works, but only a large one:**

| H3 res | Cell area | Sites/cell | Sites/km² needed to hide one among five |
| ---: | ---: | ---: | ---: |
| 9 | 10.5 ha | 1.02 | 47.5 |
| 8 | 73.7 ha | 1.21 | 6.8 |
| 7 | 516 ha | 2.94 | 0.97 |
| **6** | **36 km²** | **14.8** | **0.14** |

The last column does not depend on the synthetic population — it is how thickly
EIA'd sites would have to occur on the ground for a cell of that size to hide
one among five. Roughly seven per square kilometre, everywhere, for a 74 ha
cell. That does not happen.

So the location must be generalised to something like a 36 km² cell. **At that
scale the library answers "what habitats are typical around here", not "what is
on this site"** — a prior, not an answer.

---

## What this means for the feature

### It cannot be: upload a PDF → auto-strip → publish → look up by site

Three independent reasons, any one of which is sufficient:

1. 30.8% of identifiers survive automated stripping, and the residue includes
   the class no pattern can reach.
2. The geometry re-identifies the site regardless of the text.
3. **Protected-species locations are themselves sensitive.** Badger setts, great
   crested newt ponds and raptor nests are withheld from public datasets in the
   UK because publishing them enables persecution and disturbance — the NBN
   Atlas blurs sensitive records for exactly this reason. A library of EIA
   findings is, in substantial part, a map of where the protected species are.
   This is an ecological harm rather than a privacy one, and it is not fixed by
   anonymising the client.

### It could be: a structured findings layer, coarsely located, uploader-declared

Four changes, and the tests point at each:

- **Publish records, not documents.** Extract a typed record — habitat type,
  condition, area, BNG units, survey month, species present as a controlled
  vocabulary — and never pass prose through. A field of type `habitat_type`
  cannot contain "Bloor Homes". This turns ingestion from "read and redact"
  into "read and extract into a schema", and **the schema becomes the safety
  boundary** rather than a regex. It is the single highest-leverage change here.
- **The uploader declares their own identifiers** — client, site name,
  surveyor — and those strings are struck everywhere, including variants. This
  is the only thing that fixes the `BHSE` / `Bloor's` class.
- **Location is a coarse cell, stated as such**, with sensitive species either
  excluded or generalised further.
- **Human review before publication.** At 30.8% this is not optional, and it
  caps throughput — which is a product constraint, not a detail.

Note the tension the doc does not flag: it wants **contributor attribution**
*and* client anonymity. Naming the consultancy that produced a report narrows
the client enormously — consultancies work regionally, and a firm's client list
is often on its own website. Attribution should probably be to a contributor
account, not to a named consultancy, at least on the record itself.

### The blocker that is not technical

An EIA report is commissioned work and generally the client's property. A
consultant uploading one may have no right to publish it, anonymised or not.
**That question has to be answered before any of the above matters**, and no
amount of engineering settles it — it is the same shape as the Sentinel-2
licence question in `BLOCKERS.md §6`: cheap to ask, expensive to get wrong,
and nobody in this repo can answer it.

---

## How far to trust these numbers

Not very, and the asymmetry is the point.

The corpus was written by the same author as the redactor that scores it. That
makes a **failure meaningful and a pass weak**: text written by someone who knew
what the redactor does still leaked 30.8% of its identifiers, so a real
consultancy's report will leak more. A clean score would have proved only that
the obvious cases were handled.

This is the same trap recorded under "A tick is not a verification" in
`HANDOFF.md` — the first NDVI run printed a tick because every value fell inside
−1..1, which a pipeline averaging unmasked cloud passes comfortably.

Test B is on the firmer ground of the two: it is geometry, the method is the
obvious one an attacker would use, and the k=5 density column holds regardless
of how many sites there really are.

**Untested:** whether enough public-sector EIAs exist in machine-readable form
to seed the library, which is the other thing that decides viability. The
sandbox proxy refuses every host that could answer it (`BLOCKERS.md §1`).

**Next step, if this is worth pursuing:** a few hundred real EIA PDFs and
someone who is not the author checking the output. Everything above is a reason
to do that before writing an upload button, not a substitute for it.
