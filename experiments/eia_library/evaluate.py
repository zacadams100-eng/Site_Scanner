"""Score a de-identifier on the corpus.

Two numbers, and reporting only one of them is how this goes wrong.

**Leak rate** — the fraction of `must_remove` strings still present after
redaction. This is the safety number, and the only acceptable value on a
feature that publishes to strangers is zero. It is also the easy one to
optimise: redact everything and it is perfect.

**Retention** — the fraction of `must_keep` strings still present. This is the
value number. A redactor that scores a zero leak rate and a low retention is
safe and worthless, and the library it fills would contain nothing anybody
would trade their own report to read.

A leak is reported with the exact string that survived, because "97% safe" is
not a thing a person can act on and "the landowner's name is still in there"
is.
"""

from __future__ import annotations

from typing import Dict, List, NamedTuple

from .corpus import Passage
from .deidentify import redact


class PassageResult(NamedTuple):
    name: str
    leaked: List[str]
    destroyed: List[str]
    n_remove: int
    n_keep: int
    redacted: str

    @property
    def clean(self) -> bool:
        return not self.leaked


class Score(NamedTuple):
    results: List[PassageResult]

    @property
    def leaks(self) -> List[str]:
        return [s for r in self.results for s in r.leaked]

    @property
    def destroyed(self) -> List[str]:
        return [s for r in self.results for s in r.destroyed]

    @property
    def leak_rate(self) -> float:
        total = sum(r.n_remove for r in self.results)
        return len(self.leaks) / total if total else 0.0

    @property
    def retention(self) -> float:
        total = sum(r.n_keep for r in self.results)
        if not total:
            return 1.0
        return 1 - len(self.destroyed) / total

    @property
    def clean_passages(self) -> int:
        return sum(1 for r in self.results if r.clean)


def _present(needle: str, haystack: str) -> bool:
    """Case-insensitive containment.

    Case-insensitive because a leak is a leak whether or not the header shouted
    it: `OCKHAM ROAD NORTH` in a title block identifies the site exactly as
    well as the sentence-case version in the body.
    """
    return needle.lower() in haystack.lower()


def score(corpus: List[Passage]) -> Score:
    results = []
    for p in corpus:
        out, _ = redact(p.text)
        results.append(PassageResult(
            name=p.name,
            leaked=[s for s in p.must_remove if _present(s, out)],
            destroyed=[s for s in p.must_keep if not _present(s, out)],
            n_remove=len(p.must_remove),
            n_keep=len(p.must_keep),
            redacted=out,
        ))
    return Score(results)


def format_score(label: str, s: Score) -> str:
    lines = [
        f"{label}",
        f"  passages            {len(s.results)}",
        f"  identifiers         {sum(r.n_remove for r in s.results)}",
        f"  LEAKED              {len(s.leaks)}  ({s.leak_rate:.1%})",
        f"  findings retained   {s.retention:.1%}"
        f"  ({sum(r.n_keep for r in s.results) - len(s.destroyed)}"
        f"/{sum(r.n_keep for r in s.results)})",
        f"  fully clean         {s.clean_passages}/{len(s.results)} passages",
    ]
    if s.leaks:
        lines.append("  leaks:")
        for r in s.results:
            for leak in r.leaked:
                lines.append(f"    {r.name:26} {leak!r}")
    if s.destroyed:
        lines.append("  findings destroyed:")
        for r in s.results:
            for d in r.destroyed:
                lines.append(f"    {r.name:26} {d!r}")
    return "\n".join(lines)


def summary() -> Dict[str, Score]:
    from .corpus import DEV_CORPUS, HELDOUT_CORPUS
    return {"dev": score(DEV_CORPUS), "heldout": score(HELDOUT_CORPUS)}
