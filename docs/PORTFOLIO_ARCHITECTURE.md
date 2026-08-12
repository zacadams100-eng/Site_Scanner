# Portfolio architecture

**Partly implemented.** `portfolio.py` and `routes_portfolio.py`, 36 tests in
`tests/test_portfolio.py` and `tests/test_portfolio_route.py`. No storage.

The product's second question. The first is *"tell me about this site"*; this is
*"tell me about all of these sites"* — a different question rather than the same
one repeated. The answer a portfolio owner needs is not a thousand reports but
the handful of places in them that need a person.

---

## Structure

```
Portfolio    id · name · entries[]
  SiteEntry  site_id · name · geometry · area_ha
             records{ scanner_id → record summary }
             source (drawn | imported | demo) · added_at
```

An entry holds **summaries**, never records. A portfolio of a thousand sites
would otherwise be a hundred-megabyte document that has to be rebuilt whenever
one site is reassessed, in order to show twelve fields per row. A test asserts
the heavy parts of a real record never reach it.

Records live wherever records live. This module takes them as input and never
fetches, which is what keeps it testable and the storage decision open.

---

## The Portfolio Radar

```
1,204 sites   ·   310 never scanned   ·   87 investigations open
214 evidence gaps   ·   42 awaiting review
```

Every number is a count of something present in the records supplied. Nothing is
modelled, estimated or extrapolated. **A portfolio statistic is acted on across a
thousand sites at once**, which makes it the most damaging place in the product
to derive a number.

Three decisions in it:

**`sites_unassessed` sits beside the findings, at the same weight.** "87
investigations" without "310 never scanned" invites a reader to treat the
remainder as clear — and at portfolio scale that reading is made once and
applied to every site. It is the denominator of everything else.

**Factor gaps and domain gaps are counted separately.** They are different work.
A factor gap may close on a re-run; a domain gap needs a source that does not
exist, and telling an owner to re-run will not close it.

**Coverage is reported per scanner.** An owner reading "1,204 sites" needs to
know Water has seen forty.

---

## Ordering is not ranking

Rows sort: sites with findings, then sites never assessed, then the rest. Every
value that produced the order is a column the row displays, so a reader can see
why a site is where it is.

A computed score is the same ordering with the reasoning removed. A portfolio is
where the pressure to add one is highest, because a column that sorts is worth
money to a buyer. A test greps the served document for one.

Unassessed sites sort **above** assessed-and-clear ones deliberately: they are
the work outstanding, and a list that buried them at the bottom would hide the
portfolio's real state behind its completed part.

---

## Merging

A site assessed by Land in March and by Water in August is **one site with two
records**, not two sites. Getting this wrong would inflate every count by exactly
the amount of work that had been done — the most misleading direction for an
error to run.

Latest wins per scanner, by `assessed_at`. An undated record loses to a dated
one: an undated record is of unknown age and should not displace one whose age is
known.

---

## Demonstration data

`demo_portfolio.py` is the only place in this product that serves generated
evidence on purpose, so the labelling **is** the safety mechanism rather than a
courtesy. The rules, each with its reason:

| Rule | Why |
| --- | --- |
| Stamped on record, entry and every row | A row that is copied, exported or screenshotted must carry its own label; a legend does not survive the journey |
| Named "Demonstration site 07" | "Marsh Farm, Kent" would produce a document that looks exactly like a real assessment of somebody's land |
| Findings read from the real rules | A demo that invented finding text would misrepresent what the product says as well as what it found |
| Provenance says `generated` | A reader following a demo finding to its source is told exactly what produced it |
| Seeded, not random | A screenshot must match the screen, and `record_id` must survive a deploy |
| Six of 24 sites never assessed | `sites_unassessed` is the radar's most important number; a demo where everything had been scanned would hide it |
| Most sites quiet | Four sites in five carrying a finding reads as an alarm, not an instrument |
| No history, no trends | A fabricated past is the one thing indistinguishable from the real longitudinal record this product intends to build |

---

## Not built

**Storage.** Bound up with authentication, which does not exist. Building a
store now would guess at a data model whose main constraint has not been decided.
Everything downstream of one is built and tested; when a store arrives it fills
`entries` and nothing else changes.

**A job queue.** Assessing ten thousand sites is ten thousand assessments. The
radar counts what has been assessed rather than what has been added, so the
absence is visible rather than hidden.

**Change detection across records.** The record makes it possible — stable site
ids, versions, timestamps. Nothing consumes two records yet.

**A portfolio UI.** The API and the demonstration portfolio exist; no screen
renders them.

### What a store must guarantee

1. Records immutable; a correction is a new record.
2. `site_id` is the grouping key, not a row id.
3. Demo and real sites are never stored in one collection without the
   `source` field, and `source` is never inferred.
4. Paging, not one large POST. The 2,000-record cap on `/api/portfolio` is a
   statement about one HTTP request, not about how large a portfolio may be.
