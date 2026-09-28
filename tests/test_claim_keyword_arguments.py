# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim may pass a keyword argument to a function it names, as the
function's own callers do (`slugify(value, allow_unicode=True)`), with a
literal or a quantified name as the value. The statement keeps the
keyword as written; the probe calls the function with it; the derive
route binds it to the parameter it names, and declines rather than
drop one it cannot place. The grammar's own functions keep their fixed
keywords, and argument unpacking is still refused."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim


def scaled(x: float, k: float = 1.0) -> float:
    """x times k."""
    return k * x


def tagged(s: str, *, upper: bool = False) -> str:
    """s, upper-cased when asked."""
    return s.upper() if upper else s


def test_the_statement_keeps_the_keyword_as_written():
    c = claim("for x in [0, 1], scaled(x, k=2) == 2 * x")
    assert "k=2" in c.lhs


def test_the_derive_route_binds_a_keyword_to_its_parameter():
    (p,) = check_conjectures(scaled, [claim("for x in [0, 1], scaled(x, k=2) == 2 * x")])
    assert p.verdict == "proven", p.note
    (q,) = check_conjectures(scaled, [claim("for x in [0, 1], f(x, k=3) == 2 * x")])
    assert q.verdict == "falsified", q.note


def test_the_probe_calls_with_the_keyword():
    (p,) = check_conjectures(tagged, [claim(
        'for s in {"a", "b"}, tagged(s, upper=True) == tagged(s, upper=True)')])
    assert p.verdict in ("proven", "holds"), p.note
    (q,) = check_conjectures(tagged, [claim(
        'for s in {"a", "b"}, tagged(s, upper=True) == s')])
    assert q.verdict == "falsified", q.note


def test_a_quantified_parameter_can_be_the_keyword_s_value():
    (p,) = check_conjectures(scaled, [claim("for x in [0, 1], k in {2, 3}, scaled(x, k=k) == k * x")])
    assert p.verdict in ("proven", "holds"), p.note


@pytest.mark.parametrize("law", [
    "for x in [0, 1], scaled(x, **{'k': 2}) == 2 * x",
    "for x in [0, 1], scaled(x, k=x + 1) == x",
    "for x in [0, 1], sin(x, k=2) == x",
])
def test_what_stays_refused(law):
    with pytest.raises(InvalidConjecture):
        claim(law)


def test_the_record_s_statement_keeps_the_keyword():
    (p,) = check_conjectures(scaled, [claim("for x in [0, 1], scaled(x, k=2) == 2 * x")])
    assert "scaled(x, k=2)" in p.statement, p.statement
    (q,) = check_conjectures(tagged, [claim('for s in {"a", "b"}, tagged(s, upper=True) == s')])
    assert "tagged(s, upper=True)" in q.statement, q.statement


def test_claims_differing_only_in_a_keyword_render_differently():
    from mathema.grammar import render_law_expr
    two = render_law_expr("scaled(x, k=2)", frozenset({"scaled"}))
    three = render_law_expr("scaled(x, k=3)", frozenset({"scaled"}))
    assert two == "scaled(x, k=2)" and three == "scaled(x, k=3)"
