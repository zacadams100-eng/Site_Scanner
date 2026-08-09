# AI risk

**Status: 🟢 LOW, and unusually so. The architecture already forbids the
failure this audit exists to find.**

Everything below was verified by reading `nlq.py`, `summary.py` and
`routes_catalog.py`, not inferred from documentation.

---

## 1. What is actually sent to Anthropic

Two call sites, both optional.

### `summary.py` — the plain-English site summary

`build_prompt()` assembles a text block from **computed aggregates only**:

- the year analysed
- area in hectares
- mean NDVI, with a band label
- land-cover composition percentages
- a flood proxy value, explicitly labelled *"NOT Environment Agency flood zone
  data"* inside the prompt itself
- a screening score

### `nlq.py` — rephrasing an answer

Sends `answer["answer"]`: a sentence **already computed from the series**. The
system prompt is *"Do not add, remove or alter any number, year or factor
name."*

### What is never sent

| | Sent? |
| --- | --- |
| The drawn geometry | **No** |
| Coordinates of any kind | **No** |
| Postcode, address or place name | **No** |
| Site or project name | **No** |
| Marker names the user typed | **No** |
| Uploaded files | **No** (no upload path exists) |
| User identity | **No** (no accounts exist) |

A hectare figure and an NDVI mean are not a location. This is a stronger
privacy position than most spatial products have, and it happened by design —
worth not losing.

---

## 2. The rule that matters, and how it is enforced

> **AI must never fabricate a statistic.**

The architecture is already the one the audit asks for:

```
real analytical result  →  structured data  →  AI rephrases  →  human-readable
```

and never

```
AI  →  invented analysis
```

Three things enforce it:

1. **The model is never asked what the numbers are.** It receives a finished
   answer and is told to rewrite it. It is not given the question without the
   answer.
2. **Provenance is recorded separately from prose.** `answered_from` stays
   `"series"` whether or not a model was involved; `phrased_by` says who wrote
   the words. The two cannot be confused downstream.
3. **The deployed URL has no `ANTHROPIC_API_KEY`.** Every AI path degrades to
   the deterministic text, so the live product's numbers do not depend on a
   model being available or correct.

**The worst a bad rewrite can do is read badly, not be wrong.** That is the
design claim, and it holds as long as rule 1 does.

---

## 3. Residual risks

| Risk | Severity | Position |
| --- | --- | --- |
| A rewrite drops a caveat that was inside a sentence | MEDIUM | `insights.py` deliberately puts "demo data — generated, not observed" *inside* the sentence rather than in a sibling field, precisely so no layout can drop it — but a model rewriting the sentence could. **No test currently asserts the caveat survives rephrasing.** |
| A rewrite changes a number | LOW | Instructed against; not verified by assertion. A post-check comparing numerals before and after would close this cheaply. |
| Prompts or responses stored | LOW | Nothing writes them to disk. `telemetry.py` logs route, status and duration only — no question text, asserted by test. |
| Automated decision-making under GDPR Art. 22 | LOW today | No accounts, no profiles, no decisions about people. Would change if the product ever scored an applicant rather than a site. |
| Customer relies on an AI sentence as advice | MEDIUM | See `docs/CLAIMS_AUDIT.md`. This is a wording risk, not an AI risk. |

---

## 4. Recommended, cheap, not yet done

1. **Assert the caveat survives a rephrase.** If a finding's text contains
   "demo data", the rephrased text must too — otherwise reject the rewrite and
   keep the deterministic sentence. Two lines and a test.
2. **Assert no new numerals appear.** Extract numbers from input and output; if
   the output contains one the input did not, discard the rewrite. This turns
   the design claim in §2 into something enforced rather than instructed.

Both are follow-ups, not blockers, because the deployed product has no API key
and therefore no model in the path at all.
