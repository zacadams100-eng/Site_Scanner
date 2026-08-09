"""Natural-language questions about a drawn area.

    "has tree cover dropped near this site since 2019?"

The design decision that matters is the order of operations. A language model
parses the *question*; it never produces the *answer*. Factors and a time range
come out of the text, the answer is computed arithmetically from the series
that came back, and a model — when there is an API key — is only ever allowed
to rephrase a sentence that was already true.

Two reasons, in order of importance:

1. A model asked "did tree cover drop?" will answer confidently from nothing.
   This app's whole discipline is that a number on screen came from somewhere,
   and handing the summary sentence to a model that has not seen the data is
   the fastest way to break that.
2. The deployed URL has no ANTHROPIC_API_KEY. A feature that only works with
   one is a demo, not a feature. Everything here runs with no credentials.

What it refuses to do is as important as what it does: it will not call a
change a trend when the change is inside the year-to-year noise, it will not
answer about a factor without saying whether that factor is observed or
generated, and it will not silently pick a factor when the question did not
name one it recognises.
"""

from __future__ import annotations

import re
import re as _re
from typing import Any, Dict, List, Optional, Tuple

import catalog

# Words that carry no signal when matching a question to a factor. Deliberately
# short: this is a stop list, not a linguistic model, and every word removed
# here is one that can no longer disambiguate two factors.
STOPWORDS = frozenset("""
a an and are around as at be been by can did do does for from has have how in
into is it its me my near of on or over per site than that the their there this
to was were what when where which will with within you your average avg
year years yr
""".split())

# Question words that decide what kind of answer is wanted.
TREND_WORDS = frozenset("""
dropped drop dropping fallen fall fell falling declined decline declining
decreased decrease decreasing increased increase increasing risen rise rising
rose grown grow growing changed change changing trend trending worse better
improved improving worsened
""".split())

EXTREME_WORDS = frozenset("""
highest lowest maximum minimum max min peak worst best driest wettest hottest
coldest greenest
""".split())

LEVEL_WORDS = frozenset("""
average mean typical level value much many what
""".split())

# Phrasings the catalogue's own names do not contain. Kept small and specific —
# a large synonym table becomes a second, unmaintained copy of the catalogue.
SYNONYMS: Dict[str, Tuple[str, ...]] = {
    "tree": ("tree", "trees", "woodland", "forest", "canopy"),
    "vegetation": ("vegetation", "green", "greenness", "greenest", "vigour", "vigor", "ndvi"),
    "rain": ("rain", "rainfall", "precipitation", "wet", "wettest", "driest"),
    "temperature": ("temperature", "temp", "hot", "hottest", "heat", "warm",
                    "warmest", "cold", "coldest"),
    "flood": ("flood", "flooding", "flooded"),
    "price": ("price", "prices", "value", "cost", "expensive", "affordable"),
    "crime": ("crime", "crimes", "burglary", "antisocial", "safety"),
    "soil": ("soil", "moisture", "damp"),
    "built": ("built", "building", "buildings", "development", "developed", "urban"),
}

MIN_SCORE = 1.0
MAX_FACTORS = 3


def _words(text: str) -> List[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS]


def _expand(words: List[str]) -> set:
    """Question words plus any synonym group they belong to."""
    out = set(words)
    for w in words:
        for key, group in SYNONYMS.items():
            if w in group:
                out.update(group)
                out.add(key)
    return out


def _factor_terms(factor: Dict[str, Any]) -> set:
    """Every word that should make a factor match."""
    text = f"{factor['id']} {factor['name']} {factor.get('group', '')}"
    return _expand(_words(text.replace("_", " ")))


def match_factors(question: str, limit: int = MAX_FACTORS) -> List[Tuple[str, float]]:
    """Factors the question plausibly refers to, best first.

    Scored by overlap rather than by a model so this runs with no credentials.
    A factor whose *name* matched scores above one that only matched via its
    group, so "tree cover" prefers the tree cover factor over every other
    factor filed under Vegetation.
    """
    literal = set(_words(question))
    asked = _expand(_words(question))
    if not asked:
        return []

    scored: List[Tuple[str, float]] = []
    for factor in catalog.FACTORS:
        # Only the question is expanded. Expanding both sides makes any two
        # members of a synonym group match with the weight of the whole group,
        # so "rainfall" scored `wet_days` above precipitation totals purely
        # because both sides inflated to the same four words.
        name_terms = set(_words(factor["name"].replace("_", " ")))
        id_terms = set(_words(factor["id"].replace("_", " ")))
        group_terms = set(_words(str(factor.get("group", ""))))

        # A word the user actually typed is worth more than one reached through
        # a synonym, which is what keeps "tree cover" on the tree cover factor.
        score = (
            3.0 * len(literal & name_terms)
            + 1.5 * len((asked - literal) & name_terms)
            + 1.5 * len(literal & id_terms)
            + 0.75 * len((asked - literal) & id_terms)
            + 0.5 * len(asked & group_terms)
        )
        # Normalised by name length so a long name does not win by having more
        # words available to match.
        if name_terms:
            score /= len(name_terms) ** 0.5
        if score >= MIN_SCORE:
            scored.append((factor["id"], score))

    scored.sort(key=lambda p: (-p[1], p[0]))
    return scored[:limit]


def parse_years(question: str, first: int, last: int) -> Tuple[int, int]:
    """The year range a question is asking about.

    Defaults to the full available range, because "has tree cover dropped"
    without a date means "ever", not "this year".
    """
    q = question.lower()

    m = re.search(r"between\s+(\d{4})\s+and\s+(\d{4})", q)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return max(first, min(a, b)), min(last, max(a, b))

    m = re.search(r"\b(?:since|after|from)\s+(\d{4})", q)
    if m:
        return max(first, int(m.group(1))), last

    m = re.search(r"\b(?:before|until|up to)\s+(\d{4})", q)
    if m:
        return first, min(last, int(m.group(1)))

    m = re.search(r"\b(?:last|past)\s+(\d+)\s+years?", q)
    if m:
        return max(first, last - int(m.group(1)) + 1), last

    m = re.search(r"\bin\s+(\d{4})", q)
    if m:
        y = int(m.group(1))
        if first <= y <= last:
            return y, y

    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", q)]
    inrange = [y for y in years if first <= y <= last]
    if len(inrange) >= 2:
        return min(inrange), max(inrange)
    if len(inrange) == 1:
        return inrange[0], last

    return first, last


def parse_intent(question: str) -> str:
    # Deliberately not `_words`: the stop list removes "average" and "year",
    # which carry no signal for *which factor* but decide what kind of answer
    # is wanted. Filtering before reading intent silently turned every
    # "what was the average..." into a trend question.
    words = set(re.findall(r"[a-z0-9]+", question.lower()))
    if words & TREND_WORDS:
        return "trend"
    if words & EXTREME_WORDS:
        return "extreme"
    if words & LEVEL_WORDS:
        return "level"
    return "trend"


def interpret(question: str, first_year: int, last_year: int) -> Dict[str, Any]:
    """What the question is asking, before any data is fetched."""
    matches = match_factors(question)
    from_year, to_year = parse_years(question, first_year, last_year)
    return {
        "factor_ids": [fid for fid, _ in matches],
        "scores": {fid: round(score, 2) for fid, score in matches},
        "from_year": from_year,
        "to_year": to_year,
        "intent": parse_intent(question),
    }


def _in_range(annual: List[Dict[str, Any]], lo: int, hi: int) -> List[Dict[str, Any]]:
    return [a for a in annual
            if lo <= a["year"] <= hi and a.get("value") is not None]


def _spread(rows: List[Dict[str, Any]]) -> float:
    """Typical year-to-year movement, used as the noise floor.

    A change smaller than the average step between consecutive years is not a
    trend, it is the series wobbling. Comparing against this rather than a
    fixed percentage is what stops the answer announcing a 3% "decline" in a
    factor that moves 8% every year on its own.
    """
    if len(rows) < 2:
        return 0.0
    steps = [abs(rows[i]["value"] - rows[i - 1]["value"]) for i in range(1, len(rows))]
    return sum(steps) / len(steps)


# How much less-observed than its neighbours a year may be and still be
# compared with them. One month of slack absorbs the ordinary cloudy winter;
# beyond that the year is averaging a different set of seasons.
_COVERAGE_SLACK = 1


def _comparable(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Drop years too thinly observed to be compared with their neighbours.

    A trend is the difference between two endpoints, so a short endpoint is the
    one place a coverage artefact turns directly into a reported change. The
    failure is concrete: ask this in August and the current year holds January
    to July — the warm half — so a temperature series with no trend in it at
    all reports a rise, and the noise floor cannot catch it because a stable
    series has a noise floor of zero. That is the worst case, not an edge one:
    the steadier the factor, the more reliably a missing autumn is narrated as
    a trend.

    The test is deliberately **relative to the series**, not against twelve.
    Sentinel-2 never sees a January, so every NDVI year has nine or ten months
    and an absolute threshold would refuse to answer any question about
    vegetation at all. What matters is whether a year is short *compared with
    the years it is being measured against*, so the yardstick is the median
    coverage of the range itself.

    Returns the rows unchanged when the coverage is not recorded — an older
    cached response, or a source that does not report it. Silently dropping
    every row would turn a missing field into "no data", which is a worse
    answer than the slightly-too-confident one it replaced.
    """
    observed = [r.get("months_observed") for r in rows]
    if any(o is None for o in observed) or len(rows) < 2:
        return rows

    ordered = sorted(observed)
    median = ordered[len(ordered) // 2]
    floor = median - _COVERAGE_SLACK
    return [r for r in rows if r["months_observed"] >= floor]


def _years(years: List[int]) -> str:
    """'2026', '2011 and 2026', '2011, 2019 and 2026'."""
    items = [str(y) for y in years]
    if len(items) <= 1:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _fmt(value: float, unit: str) -> str:
    if unit == "%":
        return f"{value:.1f}%"
    if abs(value) >= 100:
        return f"{value:,.0f} {unit}".strip()
    return f"{value:.2f} {unit}".strip()


def answer_one(
    factor: Dict[str, Any],
    series: Dict[str, Any],
    from_year: int,
    to_year: int,
    intent: str,
) -> Dict[str, Any]:
    """One factor's answer, computed from its annual rollup.

    Every branch that cannot answer says why rather than producing a number.
    """
    name = factor["name"]
    unit = factor.get("unit") or ""
    source = series.get("source", "generated")
    rows = _in_range(series.get("annual") or [], from_year, to_year)

    base: Dict[str, Any] = {
        "factor_id": factor["id"],
        "label": name,
        "unit": unit,
        "source": source,
        "observed": source != "generated",
    }

    if not rows:
        return {**base, "verdict": "no-data",
                "text": f"No observations of {name} between {from_year} and {to_year}."}

    if factor.get("kind") == "categorical":
        latest = rows[-1]
        return {**base, "verdict": "level", "from": rows[0]["year"], "to": latest["year"],
                "text": f"{name} in {latest['year']}: {latest['value']}."}

    # Years too thinly observed to compare with their neighbours are set aside
    # before anything is computed from them. A short endpoint turns a coverage
    # artefact straight into a reported trend, and a short year anywhere in the
    # range drags the mean toward whichever seasons it happens to hold.
    # `_comparable` measures against the range's own median, so it can never
    # return nothing — the median-coverage rows always survive their own test.
    # That is why there is no "everything was too short" branch here: it would
    # be unreachable, and unreachable code that looks like a safety net is
    # worse than none. A test pins the invariant.
    usable = _comparable(rows)
    dropped = [r["year"] for r in rows if r not in usable]
    if dropped and len(usable) < 2 and intent != "level":
        return {**base, "verdict": "no-data",
                "text": (f"Only {usable[0]['year']} has enough of {name} observed to "
                         f"compare in that range — {_years(dropped)} had too few "
                         f"months.")}
    rows = usable

    # Said once, appended to whichever answer follows. Silently excluding a
    # year the user can see in the table is the kind of quiet disagreement
    # between two views of one number this project refuses everywhere else.
    caveat = (f" {_years(dropped)} {'was' if len(dropped) == 1 else 'were'} left out: "
              f"too few months observed to compare with the rest."
              if dropped else "")

    first, last = rows[0], rows[-1]
    values = [r["value"] for r in rows]
    mean = sum(values) / len(values)

    if intent == "level":
        return {**base, "verdict": "level", "from": first["year"], "to": last["year"],
                "mean": round(mean, 4),
                "text": (f"{name} averaged {_fmt(mean, unit)} "
                         f"across {first['year']}–{last['year']}.")}

    if intent == "extreme":
        hi = max(rows, key=lambda r: r["value"])
        lo = min(rows, key=lambda r: r["value"])
        return {**base, "verdict": "extreme",
                "high_year": hi["year"], "low_year": lo["year"],
                "text": (f"{name} was highest in {hi['year']} at {_fmt(hi['value'], unit)} "
                         f"and lowest in {lo['year']} at {_fmt(lo['value'], unit)}."
                         + caveat)}

    # Trend.
    if len(rows) < 2:
        return {**base, "verdict": "no-data",
                "text": (f"Only {first['year']} has data for {name} in that range, "
                         "so there is nothing to compare it against.")}

    delta = last["value"] - first["value"]
    noise = _spread(rows)
    pct = (delta / abs(first["value"]) * 100) if first["value"] else None

    result = {**base, "verdict": "trend", "from": first["year"], "to": last["year"],
              "from_value": round(first["value"], 4), "to_value": round(last["value"], 4),
              "change": round(delta, 4),
              "change_pct": round(pct, 1) if pct is not None else None,
              "noise": round(noise, 4)}

    if abs(delta) <= noise:
        return {**result, "verdict": "flat",
                "text": (f"{name} shows no clear trend between {first['year']} and "
                         f"{last['year']} — it moved {_fmt(abs(delta), unit)}, which is "
                         f"within its typical year-to-year variation of "
                         f"{_fmt(noise, unit)}." + caveat)}

    direction = "rose" if delta > 0 else "fell"
    change = f" ({abs(pct):.0f}%)" if pct is not None else ""
    return {**result,
            "text": (f"{name} {direction} from {_fmt(first['value'], unit)} in "
                     f"{first['year']} to {_fmt(last['value'], unit)} in "
                     f"{last['year']}{change}." + caveat)}


def compose(question: str, interpretation: Dict[str, Any],
            findings: List[Dict[str, Any]]) -> str:
    """The paragraph, assembled from findings that are already true."""
    if not findings:
        return ("I could not tell which factor that question is about. Try naming "
                "one — for example \"has tree cover dropped since 2019?\"")

    parts = [f["text"] for f in findings]

    generated = [f["label"] for f in findings if not f["observed"]]
    if generated:
        which = generated[0] if len(generated) == 1 else ", ".join(generated)
        parts.append(
            f"Note that {which} {'is' if len(generated) == 1 else 'are'} demo data on "
            "this deployment, not observed measurements, so treat the figures as "
            "illustrative.")

    return " ".join(parts)


def ask(question: str, factors_series: Dict[str, Dict[str, Any]],
        interpretation: Dict[str, Any]) -> Dict[str, Any]:
    """Answer a question from series already fetched for its factors."""
    findings = []
    for fid in interpretation["factor_ids"]:
        series = factors_series.get(fid)
        factor = catalog.FACTOR_BY_ID.get(fid)
        if not series or not factor:
            continue
        findings.append(answer_one(factor, series, interpretation["from_year"],
                                   interpretation["to_year"],
                                   interpretation["intent"]))

    return {
        "question": question,
        "understood": interpretation,
        "findings": findings,
        "answer": compose(question, interpretation, findings),
        "answered_from": "series",
    }


def rephrase(answer: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
    """Optionally let a model make the answer read better.

    It is given the computed sentences and told to rewrite them. It is never
    given the question without the answer, and never asked for a figure — so
    the worst a bad rewrite can do is read badly, not be wrong. `answered_from`
    stays "series" either way, because that is where the numbers came from.
    """
    import os

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key or not answer.get("findings"):
        return answer

    try:
        import anthropic
    except ImportError:
        return answer

    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            system=("Rewrite the given findings as one short, plain paragraph for a "
                    "non-specialist. Do not add, remove or alter any number, year or "
                    "factor name. Do not add conclusions the findings do not state."),
            messages=[{"role": "user", "content": answer["answer"]}],
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text and _rewrite_is_faithful(answer["answer"], text):
            return {**answer, "answer": text, "phrased_by": "claude"}
    except Exception:
        # A model that will not answer must never cost the user the answer that
        # was already computed without it.
        pass
    return answer


# Digits, decimals, percentages and years, as they appear in a finished
# sentence. Deliberately crude: this is a tripwire, not a parser.
_NUMERALS = _re.compile(r"\d+(?:\.\d+)?")


def _rewrite_is_faithful(original: str, rewritten: str) -> bool:
    """Is this rewrite allowed to replace the computed sentence?

    The system prompt tells the model not to alter a number and not to drop a
    caveat. An instruction is not an enforcement, and this is the enforcement.
    Both checks are one-way: a failure discards the rewrite and keeps the
    deterministic text, so the worst case is prose that reads less well.

    **No new numbers.** Every numeral in the rewrite must have appeared in the
    computed answer. The model may drop one — a summary legitimately says less
    — but inventing one is the single failure this whole architecture is
    arranged to prevent, and "we told it not to" is not a control.

    **The caveat survives.** `insights.py` puts "demo data — generated, not
    observed" *inside* the sentence rather than in a sibling field, precisely
    so no layout can drop it. A rewrite is a layout that can. If the computed
    answer carried the caveat and the rewrite does not, the rewrite is
    discarded — a fluent sentence that has quietly shed the word "demo" is
    worse than a clumsy one that kept it.
    """
    invented = set(_NUMERALS.findall(rewritten)) - set(_NUMERALS.findall(original))
    if invented:
        return False

    for caveat in ("demo data", "generated, not observed"):
        if caveat in original.lower() and caveat not in rewritten.lower():
            return False
    return True
