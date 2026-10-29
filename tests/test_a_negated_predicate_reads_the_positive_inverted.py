# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A negated predicate (`not is_defined(f)`) states that the positive
fails somewhere. A point the code is run at where the positive fails is
a witness for the negation, which is then proven; a positive that holds
at every sampled point says nothing about whether it fails elsewhere,
so the negation stays unknown; a proven positive falsifies the
negation, the proof its witness. This holds on every route, and for a
predicate over the whole function as for one over a parameter."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.types import Mat


def by_text(x: float) -> float:
    # defined at every x in [0, 1]; no symbolic or exact reading
    return float(str(x)) * 2.0


def total(x: float) -> float:
    return 2.0 * x + 1.0


def _capped(x):
    # an infinity written for |x| >= 1e300: no value there
    if abs(x) >= 1e300:
        return math.inf
    return x


def far_written(x: float) -> float:
    return _capped(float(str(x)))


def doubled_by_loop(x: float) -> float:
    # 2x by a loop: a value at every real x, its float run overflowing
    # past 9e307
    t = x
    i = 0
    while i < 1:
        t = t * 2.0
        i += 1
    return t


def grand_total(m: Mat("n", "k")) -> float:
    # the total of a matrix: a finite value at every real matrix
    return sum(sum(row) for row in m)


def recip(x: float) -> float:
    return 1.0 / x


def ratio(x: float, y: float) -> float:
    return x / y


@pytest.mark.parametrize("route", ["probe", "best", "derive"])
@pytest.mark.parametrize("fn, text", [
    (by_text, "for x in [0, 1], not is_defined(f)"),
    (total, "for x in [0, 1], not is_finite(f(x))"),
])
def test_a_sampled_pass_of_the_positive_leaves_the_negation_open(fn, text,
                                                                 route):
    # f has a value, and a finite one, at every x in [0, 1], so each
    # negation is false; sampling cannot show that, and never holds it
    (p,) = check_conjectures(fn, [claim(text, route=route)])
    assert p.verdict == "unknown", (route, p.verdict, p.route, p.note)


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_failure_of_the_positive_proves_the_negation(route):
    # 1/x has no value at x = 0, which [-1, 1] contains
    (p,) = check_conjectures(recip, [claim("for x in [-1, 1], not is_defined(f)",
                                           route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.counterexample is None
    assert "x = 0" in (p.sketch or ""), p.sketch


@pytest.mark.parametrize("route", ["probe", "best", "derive"])
def test_an_overflow_is_no_failure_of_definedness(route):
    # 2x has a value at every real x; its float run overflows to inf at
    # the largest doubles, which the body read exactly shows finite: a
    # fact about the computation (is_computation_safe), so the positive
    # is never falsified there, and the negation stays open
    (p,) = check_conjectures(doubled_by_loop, [claim("is_defined(f)", route=route)])
    assert p.verdict != "falsified", (route, p.verdict, p.counterexample)
    assert "overflow" in (p.note or ""), p.note
    (q,) = check_conjectures(doubled_by_loop, [claim("not is_defined(f)",
                                                     route=route)])
    assert q.verdict == "unknown", (route, q.verdict, q.sketch, q.note)
    assert "overflow" in (q.note or ""), q.note


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_helper_written_infinity_under_an_unreadable_body_is_undecidable(route):
    # _capped writes an infinity for |x| >= 1e300, but float(str(x))
    # stops the exact reading, so nothing tells that infinity from an
    # overflow of the computation: the point decides nothing either way
    (p,) = check_conjectures(far_written, [claim("is_defined(f)", route=route)])
    assert p.verdict == "unknown", (route, p.verdict, p.note)
    assert "cannot be told from an overflow" in p.note, p.note
    (q,) = check_conjectures(far_written, [claim("not is_defined(f)", route=route)])
    assert q.verdict == "unknown", (route, q.verdict, q.note)


@pytest.mark.parametrize("route", ["probe", "best"])
def test_an_unreadable_body_infinity_leaves_definedness_open(route):
    # float(str(x)) * 2.0: 2x has a value at every real x, but the body
    # cannot be read exactly and Python's float multiply sets no flag, so
    # the -inf at x = -1.8e308 cannot be told from a missing value
    (p,) = check_conjectures(by_text, [claim("is_defined(f)", route=route)])
    assert p.verdict == "unknown", (route, p.verdict, p.note)
    assert "-1.7976931348623157e+308" in p.note, p.note
    assert "cannot be told from an overflow" in p.note, p.note
    (q,) = check_conjectures(by_text, [claim("not is_defined(f)", route=route)])
    assert q.verdict == "unknown", (route, q.verdict, q.note)
    # is_overflow_safe and is_finite read the value returned: an infinity
    # at the largest doubles is neither overflow-safe nor finite
    (r,) = check_conjectures(by_text, [claim("is_overflow_safe(x)", route=route)])
    assert r.verdict == "falsified", (route, r.verdict, r.note)
    assert "1.7976931348623157e+308" in r.counterexample, r.counterexample
    (s,) = check_conjectures(by_text, [claim(
        "for x in [-1.7976931348623157e308, 1.7976931348623157e308], "
        "is_finite(f(x))", route=route)])
    assert s.verdict == "falsified", (route, s.verdict, s.note)
    assert "not finite" in s.counterexample, s.counterexample


@pytest.mark.parametrize("route", ["probe", "best"])
def test_a_negated_predicate_over_the_whole_function_is_inverted(route):
    # x / y raises at y = 0, so the function is not pole safe
    (p,) = check_conjectures(ratio, [claim("not is_pole_safe(f)", route=route)])
    assert p.verdict == "proven", (route, p.verdict, p.counterexample, p.note)
    assert p.statement.startswith("not "), p.statement


@pytest.mark.parametrize("route", ["probe", "best", "derive"])
def test_a_finite_total_at_the_largest_doubles_is_never_no_value(route):
    # [[M, M], [M, M]] with M the largest double totals 4M, a finite real;
    # its float run overflows to inf, and the body read exactly, nested
    # rows included, is finite there: an overflow, never a missing value
    (p,) = check_conjectures(grand_total, [claim("is_defined(f)", route=route)])
    assert p.verdict == "holds", (route, p.verdict, p.counterexample, p.note)
    (q,) = check_conjectures(grand_total, [claim("not is_defined(f)", route=route)])
    assert q.verdict == "unknown", (route, q.verdict, q.note)


def test_an_exact_reading_is_evidence_only_when_its_value_is_exact(monkeypatch):
    from fractions import Fraction

    from mathema import _exact_body
    from mathema.claim_families import _exact_reading

    def plain(x):
        return x * 2.0

    def twin_of(result):
        def make(fn):
            def run(*args, **kwargs):
                if isinstance(result, BaseException):
                    raise result
                return result
            return run
        return make

    cases = [
        (Fraction(4), "overflow"),
        (float("inf"), None),       # a float the twin computed is no reading
        (1.5, None),
        (ZeroDivisionError("division by zero"), "no value"),
        (ValueError("math domain error"), "no value"),
        (TypeError("unsupported operand"), None),   # the twin's machinery
        (AttributeError("no attribute"), None),
    ]
    for result, expected in cases:
        monkeypatch.setattr(_exact_body, "exact_callee", twin_of(result))
        assert _exact_reading(plain, (1.0,), {}) == expected, (result, expected)
