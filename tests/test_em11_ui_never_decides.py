"""
EM11 — no UI component may independently determine a finding state.

`flagged`, `clear`, `informational` and `not_assessed` are decided once, by the
evidence engine. Every interface renders that decision and none derives one.

**What this file can and cannot prove.** It is a source scan, so it catches the
realistic mistake — a component comparing a number against a threshold and
picking a state from the result — and it cannot prove the absence of every
possible local interpretation. The guarantee is architectural. This is the
tripwire, and it is worth having because the failure mode is gradual: each
screen grows one small local rule, the rules drift, and the product ends up
holding three opinions about one site.

If a test here fails, the fix is almost always to move the decision into
`radar.py` and send the state to the client, not to restructure the expression
until the scan stops noticing.
"""

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent
WEB = ROOT / "web" / "src"

#: The vocabulary. A frontend file may compare against these (reading a state
#: the server sent) but must never compute one.
STATES = ("flagged", "clear", "partial", "not_assessed", "informational")

#: Severity words are decided by the same engine and carry the same hazard.
SEVERITIES = ("high", "medium", "low")


def frontend_files():
    if not WEB.exists():                                   # pragma: no cover
        pytest.skip("frontend not present")
    return [p for p in WEB.rglob("*.ts*")
            # Type declarations are where the vocabulary is *defined*; that is
            # the one place the literals legitimately appear beside nothing.
            if p.name not in ("types.ts",)
            and not p.name.endswith(".test.ts")
            and not p.name.endswith(".test.tsx")]


def code_lines(path):
    """Lines with comments stripped.

    Without this the scan trips on the design comments that *describe* the
    rule — "the historical chart must not decide looks-like-a-decline" contains
    a state literal and would fail the file it is protecting.
    """
    out = []
    in_block = False
    for i, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw
        if in_block:
            if "*/" in line:
                line = line.split("*/", 1)[1]
                in_block = False
            else:
                continue
        if "/*" in line:
            head, rest = line.split("/*", 1)
            if "*/" in rest:
                line = head + rest.split("*/", 1)[1]
            else:
                line, in_block = head, True
        if "//" in line:
            line = line.split("//", 1)[0]
        if line.strip():
            out.append((i, line))
    return out


#: A numeric comparison. `>= 20`, `< 0.5`, `> threshold` — the shape of a rule.
COMPARISON = re.compile(r"[<>]=?\s*-?\d|\d\s*[<>]=?")

STATE_LITERAL = re.compile(
    r"""['"](""" + "|".join(STATES) + r""")['"]""")


def test_em11_no_frontend_file_derives_a_finding_state_from_a_number():
    """The realistic mistake: `value > 20 ? 'flagged' : 'clear'`.

    A component reading `state === 'flagged'` is fine — that is rendering a
    decision. A component producing `'flagged'` from a comparison is a second
    interpretation engine, and the second one always drifts from the first.
    """
    offences = []
    for path in frontend_files():
        for lineno, line in code_lines(path):
            if STATE_LITERAL.search(line) and COMPARISON.search(line):
                offences.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offences, (
        "A frontend file appears to decide a finding state from a value. "
        "Move the decision into radar.py:\n  " + "\n  ".join(offences))


def test_em11_no_frontend_file_derives_a_severity_from_a_number():
    """Severity is the same hazard with a shorter word.

    Scanned separately because `'high'`, `'medium'` and `'low'` are common
    enough in styling that they need the tighter test — the literal must be
    *produced* (after `?`, `:`, `=` or `return`) rather than merely present.
    """
    produced = re.compile(
        r"""(\?|:|=|return)\s*['"](""" + "|".join(SEVERITIES) + r""")['"]""")
    offences = []
    for path in frontend_files():
        for lineno, line in code_lines(path):
            if produced.search(line) and COMPARISON.search(line):
                offences.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offences, (
        "A frontend file appears to decide a severity from a value:\n  "
        + "\n  ".join(offences))


def test_em11_the_scan_would_actually_catch_a_violation():
    """The control.

    A scan that cannot fail is worse than no scan, because it reports safety.
    This feeds it the exact line EM11 forbids and asserts it is caught.
    """
    bad = "const state = change < -20 ? 'flagged' : 'clear'"
    assert STATE_LITERAL.search(bad) and COMPARISON.search(bad)

    # And the shapes that must NOT trip it: reading a state, and styling one.
    for good in ("if (topic.state === 'flagged') return <Dot />",
                 "className={`cmp-cell is-${cell.state}`}",
                 "const label = STATE_LABEL[cell.state]",
                 "{t.state === 'clear' ? 'checked · clear' : 'not assessed'}"):
        assert not (STATE_LITERAL.search(good) and COMPARISON.search(good)), good


def test_em11_the_finding_vocabulary_is_defined_in_exactly_one_place():
    """Two definitions of the same four states is how they drift apart.

    The server is the authority; `types.ts` mirrors it for the compiler. If a
    third list appears, one of them will eventually gain a fifth state or lose
    a fourth.
    """
    import radar

    types = (WEB / "types.ts").read_text()
    for state in ("flagged", "clear", "partial", "not_assessed"):
        assert f"'{state}'" in types, state

    # And the server's own vocabulary has not grown a fifth state without the
    # frontend, the contract documents and this test being updated together.
    assert radar.SEVERITIES == ("high", "medium", "low")


def test_em11_no_threshold_constant_lives_in_the_frontend():
    """A threshold in `web/src/` is a rule in the wrong process.

    Deliberately narrow — it looks for the naming, not for every number, since
    the frontend is full of legitimate pixel values. A reviewer should treat
    any new one as a defect until proven otherwise.
    """
    suspicious = re.compile(
        r"\b(THRESHOLD|THRESHOLDS|FLAG_AT|SEVERITY_AT|RISK_AT)\b")
    offences = []
    for path in frontend_files():
        for lineno, line in code_lines(path):
            if suspicious.search(line):
                offences.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offences, (
        "A threshold appears to be defined in the frontend:\n  "
        + "\n  ".join(offences))
