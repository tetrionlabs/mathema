# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that calls a name bound nowhere is refused (skipped, naming
the unresolved function), whether it is stated at a single point or over
a quantified domain; a bound name that genuinely raises is still a
falsification."""
import pytest

from mathema.conjecture import check_conjectures, claim


def f(a, b):
    return a * b * 4


def _row(law, route, **kw):
    return check_conjectures(f, [claim(law, route=route, **kw)])[0]


@pytest.mark.parametrize("route", ["best", "probe", "derive"])
def test_the_single_point_form_is_refused_like_the_quantified_one(route):
    single = _row("f(100.0, 0.25) == g(1)", route)
    quantified = _row("for a in [1,5], f(a, 0.25) == g(1)", route)
    assert single.verdict == quantified.verdict == "skipped"
    assert single.route == quantified.route
    marker = "could not resolve bound function(s) ['g']"
    assert marker in single.note
    assert single.note.split(marker)[1] == quantified.note.split(marker)[1]


def test_a_claim_whose_names_are_all_bound_is_unaffected():
    def g(x):
        return x * 100
    p = _row("f(100.0, 0.25) == g(1)", "probe", funcs={"g": g})
    assert p.verdict == "holds"


def test_a_bound_name_that_raises_type_error_still_falsifies():
    def g(x):
        raise TypeError("nope")
    p = _row("f(100.0, 0.25) == g(1)", "probe", funcs={"g": g})
    assert p.verdict == "falsified"
    assert "TypeError" in (p.counterexample or "") + (p.note or "")
