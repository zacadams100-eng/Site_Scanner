# EM12 (proposed) — every finding exposes its limitation

**Status: proposed, not adopted.** `EVIDENCE_MODEL.md` is unchanged. This
document states the candidate invariant and records whether the architecture
can actually satisfy it, which is the question that decides whether it is worth
adopting.

---

## The proposed invariant

> **EM12 — No finding may be presented without stating what it does not
> establish.**
>
> Every flag, informational finding, historical finding, comparison statement
> and brief entry carries a limitation alongside its claim. A surface that
> renders a finding renders both.

The reasoning is the one the product already rests on. A reader completes

    measurement → diagnosis

by default. Contour supports only

    measurement → investigation

The `evidence.py` claim boundary was built to hold that line in one place. EM12
would make it a property of the system rather than of the screen that happens
to have it.

---

## Feasibility — measured, not assumed

| Surface | Carries a limitation today? | Where from |
| --- | --- | --- |
| Evidence explorer | **Yes, every state** | `evidence.py::_claims` |
| Radar flags | **Partly** | `rule_meta.not_evidence_of` — present on **1 of 25 rules** |
| Radar informational | **No** | no field at all |
| Historical findings | Yes | inherits the flag's `rule_meta` |
| Comparison | Global only | `comparison.LIMITS`, one string per response |
| Brief | n/a | not built |

**The blocking finding: 1 of 25 rules declares a per-finding negative.**
Only `historical_vegetation_decline` has one, and it was added by hand this
week.

So EM12 **cannot** be adopted in the form "every rule declares its own
limitation". Doing that would require writing 24 bespoke negatives, which is
precisely the situation in which someone invents plausible-sounding text for a
rule they do not understand — the failure this project works hardest to avoid.

---

## The form that is satisfiable

EM12 is achievable today if stated at the level the architecture actually
supports:

> A finding's limitation is composed from **its state**, and a rule **may**
> add its own. The state-generic clause is always present; the rule-specific
> one is an addition, never a replacement.

`evidence.py` already implements exactly this. Its five clauses —
`CAUSAL_LIMIT`, `REGULATORY_LIMIT`, `CLEAR_LIMIT`, `ABSENCE_LIMIT`,
`INFORMATIONAL_LIMIT` — cover every state universally, with no per-rule text
required, and `not_evidence_of` layers on top where a rule has something
specific to say.

Under that form the gap is small and concrete:

1. **Informational findings** carry no limitation in the radar payload. They
   have one in the explorer only.
2. **Comparison** carries a single global `LIMITS` string rather than a
   limitation per statement.
3. The composer lives in `evidence.py`, which is a consumer of `radar`. To
   serve every surface it would need to be callable independently of a
   per-factor explorer entry — a refactor of about one function's worth, with
   no change to what any clause says.

---

## Recommendation

**Adopt EM12 in the satisfiable form, after the Brief is built, not before.**

Two reasons for that order. The Brief is the first artefact that must present
findings from *every* surface at once — flags, informational readings,
historical change, gaps — so it is the thing that will show whether the shared
composer is genuinely shared or whether each surface needs a special case. And
adopting an invariant before the code satisfies it means shipping a documented
promise the tests do not enforce, which is worse than not writing it down.

The order that follows from this:

1. Build the Brief, consuming `evidence.py`'s claims for every section.
2. If it needs no special cases, lift the composer so `radar.informational` and
   `comparison` can call it too.
3. Then promote EM12 to `EVIDENCE_MODEL.md` with a
   `tests/test_evidence_model.py::test_em12_*` that walks every finding in a
   full payload and asserts a non-empty limitation on each.

Step 3 is the point at which this becomes a machine-enforced product promise
rather than a convention. Until then `tests/test_evidence_explorer.py`
enforces it for the explorer alone, which is where it currently holds.
