# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Every name a claim uses is declared: a parameter of the function
under test, a name bound by `for` or `let`, a dimension of a declared
space, a variable a derivative, sum, integral or limit binds, or a
known constant or function. Anything else is refused, naming the name
and saying how to declare it, never sampled as a free variable. `=`
still means `==`."""
import pytest

from mathema.conjecture import InvalidConjecture, check_conjectures, claim
from mathema.reason_codes import ClaimReasonCode, claim_reason_code
from tests.test_claim_text_soundness import _verdict, assert_round_trips


def ident(x: float) -> float:
    return x


def with_mode(x: float, mode: str = "fast") -> float:
    return x


def summand(i: float) -> float:
    return 2.0 * i


def _probe(fn, law):
    (probe,) = check_conjectures(fn, [claim(law)])
    return probe


@pytest.mark.parametrize("law, name", [
    ("for x in [0, 1], y = f(x)", "y"),
    ("for x in [0, 1], y == f(x)", "y"),
    ('mode = "fast"', "mode"),
    ("for x in [0, 1], f(x) >= x - q", "q"),
    ("assuming z > 0, for x in [0, 1], f(x) >= x - 1", "z"),
    ("for x in [0, 1], 0 <= f(x) <= top", "top"),
    ("for x in [0, 1], 5 <= f(x) <= top", "top"),
])
def test_an_undeclared_name_is_refused_by_name(law, name):
    probe = _probe(ident, law)
    assert probe.verdict == "skipped:misspecified", (probe.verdict, probe.note)
    assert f"undeclared name {name!r}" in probe.note
    assert f"let {name} be [" in probe.note
    assert claim_reason_code(probe) == ClaimReasonCode.INVALID_CONJECTURE


def test_the_undeclared_name_is_no_longer_sampled():
    probe = _probe(ident, "for x in [0, 1], y = f(x)")
    assert probe.counterexample is None
    assert "-2.7" not in (probe.note or "")


def test_a_parameter_of_f_is_declared_without_a_for():
    assert _probe(with_mode, 'mode = "fast"').verdict != "skipped:misspecified"


@pytest.mark.parametrize("law", [
    "let y be [0, 1], for x in [0, 1], f(x) >= x - y - 1",
    "for x in [0, 1], f(x) >= x*pi - 9",
    "for x in [0, 1], abs(f(x) - x) <= ε",
    "for x in [0, 1], d(f(x), x) @ {x = 1} == 1",
    "lim(f(x), x -> 0) == 0",
    "integrate(f(x), x, 0, 1) >= 0",
])
def test_declared_and_bound_names_are_not_refused(law):
    assert _probe(ident, law).verdict in ("proven", "holds"), law


def test_a_sum_bound_is_declared_with_let():
    law = "let n be [1, 20] subset Z, Sum(f(i))_{i=1}^n == n*(n+1)"
    assert_round_trips(law, summand)
    assert _verdict(summand, claim(law)) != "skipped:misspecified"
    bare = _probe(summand, "Sum(f(i))_{i=1}^n == n*(n+1)")
    assert bare.verdict == "skipped:misspecified"
    assert "undeclared name 'n'" in bare.note


def test_a_space_dimension_is_declared_by_its_space():
    def fifth(xs: list) -> float:
        return xs[4]
    probe = _probe(fifth, "assuming n >= 5, for xs in R^n, f(xs) == xs[4]")
    assert probe.verdict == "holds", probe.note


def test_equals_still_means_equality():
    assert claim("for x in [0, 1], f(x) = x").relation == "=="
    assert _probe(ident, "for x in [0, 1], f(x) = x").verdict == "proven"


# a bare `name = expr` after a let run

@pytest.mark.parametrize("law", [
    "let alpha = 0.5, x = alpha",
    "let g = math.sqrt, r = g(q)",
])
def test_a_trailing_equation_after_a_let_run_says_what_happened(law):
    with pytest.raises(InvalidConjecture, match="reads as another `let` binding"):
        claim(law)


def test_a_let_run_with_no_statement_says_so():
    with pytest.raises(InvalidConjecture, match="no claim after"):
        claim("let alpha = 0.5, let beta = 2")


def test_the_double_equals_after_a_let_run_still_reads():
    assert claim("let alpha = 0.5, x == alpha").lhs == "x"
