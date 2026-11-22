# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined(f)` over a domain that lists a missing value (`{None}`,
`{1, None}`, `[0, 1] | absent`) states that f returns at that value
too. The body's raise region is read over the real numbers only, so
it says nothing about None: each listed value is run, and a raise
there falsifies the claim with that call as the witness. The negation
reads the same run the other way."""
import pytest

from mathema.conjecture import check_conjectures, claim


def doubled(x):
    return x * 2.0


def doubled_or_zero(x):
    if x is None:
        return 0.0
    return x * 2.0


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("text", [
    "for x in {None}, is_defined(f)",
    "for x in {1, None}, is_defined(f)",
    "for x in [0, 1] | absent, is_defined(f)",
])
def test_a_raise_at_a_listed_none_falsifies_is_defined(text):
    p = _row(doubled, text)
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)
    assert "None" in (p.counterexample or ""), p.counterexample


@pytest.mark.parametrize("text", [
    "for x in {None}, not is_defined(f)",
    "for x in {1, None}, not is_defined(f)",
])
def test_the_negation_of_is_defined_at_a_raising_none_is_not_falsified(text):
    p = _row(doubled, text)
    assert p.verdict != "falsified", (p.verdict, p.route, p.counterexample)


def test_a_function_that_returns_at_none_is_still_proven_defined():
    p = _row(doubled_or_zero, "for x in {1, None}, is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)


def test_is_defined_over_the_numbers_alone_still_proves():
    p = _row(doubled, "for x in [0, 1], is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
