# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A type clause that admits exactly the missing values the domain
would admit unstated names none of them. The rendered text of a claim
over an interval or a named type writes that default out in full
(`[1.0, 5.0] : float|absent|missing` for a claim read without its
function, `[1.0, 5.0] : float|missing` beside a `float` parameter), so
reading a statement or a canonical text back gives the claim that was
rendered, with the same verdict. A value the text adds to the default
or names in a set (`{1, None}`, `[0, 1] | {None}`, `: float|absent`
beside a `float` parameter) is named, and the claim is judged at it."""
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.spec import canonical_claim_text, entry_claims, render_claim_text


def ident(x: float) -> float:
    return x


def unannotated(x):
    return x


def minus_one_when_absent(x: Optional[float]) -> float:
    if x is None:
        return -1.0
    return x


def minus_one_when_absent_float(x: float) -> float:
    if x is None:
        return -1.0
    return x


def minus_one_when_nan(x: float) -> float:
    if x is None:
        return -1.0
    return -1.0 if x != x else x


def _row(fn, cj):
    (row,) = check_conjectures(fn, [cj])
    return row


def _from_record(text):
    (rebuilt,) = entry_claims({"claims": [{"name": "c", "statement": text}]})
    return rebuilt


UNNAMED = [
    (ident, "for x in [1, 5], f(x) == x"),
    (ident, "for x in [1, 5], f(x) >= 0"),
    (ident, "for x in R, f(x) == x"),
    (unannotated, "for x in [1, 5], f(x) == x"),
    (minus_one_when_absent, "for x in [0, 1], f(x) >= 0"),
    (ident, "let root = math.sqrt, for x in [1, 100], root(x) >= 0"),
]


@pytest.mark.parametrize("fn, text", UNNAMED, ids=[f"{fn.__name__}: {t}" for fn, t in UNNAMED])
def test_a_rendered_claim_reads_back_with_the_verdict_it_had(fn, text):
    cj = claim(text)
    first = _row(fn, cj)
    assert first.verdict != "falsified", (first.verdict, first.note)
    for rendered in (canonical_claim_text(cj),
                     render_claim_text(cj, unicode=False),
                     render_claim_text(cj, unicode=True),
                     first.statement):
        again = _row(fn, claim(rendered))
        assert again.verdict == first.verdict, (rendered, again.verdict,
                                                again.counterexample, again.note)


def test_a_canonical_text_read_from_a_record_keeps_its_verdict():
    cj = claim("for x in [1, 5], f(x) == x")
    text = canonical_claim_text(cj)
    assert text == "for x in [1.0, 5.0] : float|absent|missing, f(x) = x"
    assert _row(ident, _from_record(text)).verdict == "proven"


def test_a_statement_beside_a_float_parameter_keeps_its_verdict():
    first = _row(ident, claim("for x in [1, 5], f(x) == x"))
    assert first.statement == "for x in [1.0, 5.0] : float|missing, f(x) = x"
    assert _row(ident, claim(first.statement)).verdict == "proven"


NAMED = [
    (minus_one_when_absent, "for x in {1, None}, f(x) >= 0", "x = None"),
    (minus_one_when_absent, "for x in {1, absent}, f(x) >= 0", "x = None"),
    (minus_one_when_absent, "for x in [0, 1] | {None}, f(x) >= 0", "x = None"),
    (minus_one_when_absent_float, "for x in [0, 1] | {None}, f(x) >= 0", "x = None"),
    (minus_one_when_absent_float, "for x in [0, 1] : float|absent, f(x) >= 0",
     "x = None"),
    (minus_one_when_absent, "for x in [0, 1] : float|absent, f(x) >= 0", "x = None"),
    (minus_one_when_nan, "for x in [0, 1] | {nan}, f(x) >= 0", "x = nan"),
    (minus_one_when_nan, "for x in [0, 1] : float|nan, f(x) >= 0", "x = nan"),
]


@pytest.mark.parametrize("fn, text, witness", NAMED,
                         ids=[f"{fn.__name__}: {t}" for fn, t, _w in NAMED])
def test_a_named_missing_value_is_still_judged(fn, text, witness):
    row = _row(fn, claim(text))
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == witness, row.counterexample


def test_a_set_that_lists_none_is_judged_when_read_back():
    cj = claim("for x in {1, None}, f(x) >= 0")
    text = canonical_claim_text(cj)
    assert text == "for x in {1, absent}, f(x) >= 0"
    row = _row(minus_one_when_absent, _from_record(text))
    assert row.verdict == "falsified", (row.verdict, row.note)
    assert row.counterexample == "x = None", row.counterexample


def test_a_named_value_on_the_probe_route_is_still_judged():
    row = _row(minus_one_when_absent,
               claim("for x in [0, 1] | {None}, f(x) >= 0", route="probe"))
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample == "x = None", row.counterexample


def test_a_rendered_claim_on_the_probe_route_keeps_its_verdict():
    cj = claim("for x in [1, 5], f(x) == x", route="probe")
    first = _row(ident, cj)
    again = _row(ident, claim(render_claim_text(cj, unicode=False), route="probe"))
    assert first.verdict == again.verdict == "holds", (first.verdict, again.verdict,
                                                       again.note)


def _verdicts(fn, text):
    import mathema
    rec = mathema.check(fn, claims=[claim(text, name="c")])
    return {p.name: (p.verdict, p.counterexample) for p in rec.probes
            if p.name == "c" or p.name.startswith("c[")}


RESTATED = [
    (minus_one_when_absent, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0"),
    (minus_one_when_nan, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|missing, f(x) >= 0"),
    (minus_one_when_absent_float, "for x in [0, 1], f(x) >= 0",
     "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0"),
]


@pytest.mark.parametrize("fn, plain, restated", RESTATED,
                         ids=[f"{fn.__name__}: {r}" for fn, _p, r in RESTATED])
def test_every_row_of_a_restating_clause_reads_as_the_plain_interval(fn, plain, restated):
    """The mathematics row and the float companion judge a clause that
    restates the default as they judge the plain interval: the missing
    value is the policy rows' alone."""
    assert _verdicts(fn, restated) == _verdicts(fn, plain)
