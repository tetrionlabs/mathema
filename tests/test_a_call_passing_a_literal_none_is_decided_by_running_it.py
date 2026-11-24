# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim whose call to f passes a literal derive cannot read as a
real number (`None`, a string) names that one concrete call. Derive
reads every argument as a real symbol, so it would read `x is None` as
false; the call is run instead, and its result decides the claim."""
import pytest

from mathema.conjecture import check_conjectures, claim


def one_at_none(x, y=0.0):
    if x is None:
        return 1.0
    return 0.0


def one_at_word(x, y=0.0):
    if x == "on":
        return 1.0
    return 0.0


def _row(fn, text, route="best"):
    rows = check_conjectures(fn, [claim(text, route=route)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("route", ("best", "derive"))
def test_a_call_passing_none_that_breaks_the_claim_is_never_proven(route):
    p = _row(one_at_none, "for x in {1}, f(None, 0.5) == 0", route)
    assert p.verdict != "proven", (p.verdict, p.route, p.note)


def test_a_call_passing_none_that_breaks_the_claim_is_falsified():
    p = _row(one_at_none, "for x in {1}, f(None, 0.5) == 0")
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)


def test_a_call_passing_a_string_that_breaks_the_claim_is_never_proven():
    p = _row(one_at_word, "for x in {1}, f('on', 0.5) == 0")
    assert p.verdict != "proven", (p.verdict, p.route, p.note)


def test_a_call_passing_none_that_keeps_the_claim_is_not_falsified():
    p = _row(one_at_none, "for x in {1}, f(None, 0.5) == 1")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.route, p.note)


def test_a_numeric_literal_call_still_proves():
    p = _row(one_at_none, "for x in {1}, f(2, 0.5) == 0")
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
