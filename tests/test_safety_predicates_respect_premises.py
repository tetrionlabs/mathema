# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A safety predicate quantifies over the claim's premises like every
other claim, and a raise at an admitted point is no value.

`for x in [-1, 1], assuming x == 0, is_finite(f(x))` asks about x = 0
alone, so for `1.0 / x` it is falsified there with the ZeroDivisionError
named. `assuming std(returns, ddof=1) == 0` asks about constant
sequences, which random draws never produce, so the premise has a
solved draw: a constant sequence. A premise no sampled point satisfies
is `skipped`, never `holds`, and `n` counts admitted points only.
"""
import math

import numpy as np
import pandas as pd
import pytest

from mathema._exact_premises import premise_functions
from mathema._linalg_eval import FUNCTIONS
from mathema.conjecture import check_conjectures, claim

SEEN: list = []


def recip(x: float) -> float:
    SEEN.append(x)
    return 1.0 / x


def sharpe(returns: pd.Series) -> float:
    SEEN.append(list(returns))
    return float(returns.mean() / returns.std(ddof=1) * np.sqrt(252))


def sharpe_or_zero(returns: pd.Series) -> float:
    SEEN.append(list(returns))
    if max(returns) == min(returns):
        return 0.0
    return float(returns.mean() / returns.std(ddof=1) * np.sqrt(252))


def inverse_gap(x: float, y: float) -> float:
    SEEN.append((x, y))
    return 1.0 / (y - 2 * x)


def pure_recip(x: float) -> float:
    return 1.0 / x


def shifted_gap(x: float, y: float) -> float:
    SEEN.append((x, y))
    return 1.0 / (y - 2 * x + 1.0)


RETURNS = "for returns in [-0.1, 0.1]^n, "


@pytest.fixture(autouse=True)
def _fresh_calls():
    SEEN.clear()
    yield
    SEEN.clear()


def _one(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c")])
    return p


def _constant(xs) -> bool:
    return len(set(xs)) == 1


# --- the premise is read ----------------------------------------------------


def test_an_equality_premise_puts_is_finite_at_the_pole():
    p = _one(recip, "for x in [-1, 1], assuming x == 0, is_finite(f(x))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.route == "probe:algorithmic"
    assert "ZeroDivisionError" in p.counterexample
    assert SEEN and all(x == 0 for x in SEEN)


def test_an_interval_premise_keeps_is_finite_away_from_the_pole():
    p = _one(recip, "for x in [-1, 1], assuming x > 0.5, is_finite(f(x))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert SEEN and all(x > 0.5 for x in SEEN)
    # every call was at an admitted point, and only those are counted
    assert p.n == len(SEEN)


def test_a_zero_spread_premise_draws_constant_returns_and_falsifies():
    p = _one(sharpe, RETURNS + "assuming std(returns, ddof=1) == 0, "
                               "is_finite(f(returns))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert SEEN and all(_constant(xs) for xs in SEEN)
    witness = SEEN[-1]
    assert all(-0.1 <= v <= 0.1 for v in witness)
    value = sharpe(pd.Series(witness))
    assert not math.isfinite(value)


def test_a_positive_spread_premise_excludes_every_constant_draw():
    p = _one(sharpe, RETURNS + "assuming std(returns, ddof=1) > 0, "
                               "is_finite(f(returns))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert SEEN and not any(_constant(xs) for xs in SEEN)
    assert all(-0.1 <= v <= 0.1 for xs in SEEN for v in xs)
    assert p.n == len(SEEN)


def test_no_admitted_point_is_skipped_not_holds():
    # the probe stage reports skipped; with the derive half unsupported
    # the claim is unknown, as the plain probe's claims are
    p = _one(recip, "for x in [-1, 1], assuming sin(x) > 1, is_finite(f(x))")
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert ("the probe could not decide it either (no sampled point satisfied the assuming "
            "clause)") in p.note
    assert SEEN == []


def test_the_exact_filter_rejects_a_constant_that_float_arithmetic_admits():
    from mathema._premises import compile_premises, admits
    (c,) = [claim("for xs in R^n, assuming std(xs, ddof=1) > 0, "
                  "f(xs) == f(xs)")]
    from mathema.conjecture import _interpret_assumption
    assumption = _interpret_assumption(c, [c])[2]
    compiled = compile_premises(c, assumption, {"xs": "sequence"},
                                frozenset())
    words = premise_functions(FUNCTIONS)
    constant = np.array([-0.1, -0.1, -0.1])
    assert np.std(constant, ddof=1) > 0   # numpy's float residue
    assert FUNCTIONS["std"](constant, ddof=1) == 0   # the exact claim word
    assert not admits(compiled, {**FUNCTIONS, **words, "xs": constant})
    assert admits(compiled, {**FUNCTIONS, **words,
                             "xs": np.array([-0.1, 0.0, 0.1])})


# --- the plain probe draws the same surface ---------------------------------


def test_the_plain_probe_adjudicates_a_zero_spread_premise():
    # at [-0.1] * 3 pandas returns -9.34e16, a finite value, so the claim
    # that the result is missing is false there
    p = _one(sharpe, RETURNS + "assuming std(returns, ddof=1) == 0, "
                               "f(returns) in {missing}")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert SEEN and all(_constant(xs) for xs in SEEN)


@pytest.mark.parametrize("premise", [
    "var(returns, ddof=1) == 0",
    "max(returns) == min(returns)",
    "max(returns) - min(returns) == 0",
])
def test_every_zero_spread_spelling_draws_constant_returns(premise):
    p = _one(sharpe, RETURNS + f"assuming {premise}, is_finite(f(returns))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert SEEN and all(_constant(xs) for xs in SEEN)


# --- negative controls: each new path does not invent a failure -------------


def test_a_constant_draw_on_code_that_handles_constants_holds():
    p = _one(sharpe_or_zero, RETURNS + "assuming std(returns, ddof=1) == 0, "
                                       "is_finite(f(returns))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert SEEN and all(_constant(xs) for xs in SEEN)
    assert p.n == len(SEEN)


def test_a_solved_equality_premise_places_every_safety_draw_on_its_surface():
    p = _one(inverse_gap, "for x in [-1, 1], y in [-2, 2], "
                          "assuming y == 2 * x, is_finite(f(x, y))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ZeroDivisionError" in p.counterexample
    assert SEEN and all(y == 2 * x for x, y in SEEN)


def test_a_solved_equality_premise_on_code_defined_there_holds():
    p = _one(shifted_gap, "for x in [-1, 1], y in [-2, 2], "
                          "assuming y == 2 * x, is_finite(f(x, y))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert SEEN and all(y == 2 * x for x, y in SEEN)


def test_a_raise_only_outside_the_premise_is_not_a_witness():
    p = _one(recip, "for x in [-1, 1], assuming x != 0, is_finite(f(x))")
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    assert 0 not in SEEN


# --- a raise is no value ----------------------------------------------------


def test_a_raise_inside_the_domain_falsifies_is_finite():
    p = _one(recip, "for x in {0, 1}, is_finite(f(x))")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ZeroDivisionError" in p.counterexample


# --- the structural (examine) halves never witness outside the premise ------


def test_a_premise_excluding_the_pole_makes_is_pole_safe_hold():
    p = _one(pure_recip, "for x in [-1, 1], assuming x > 0.5, is_pole_safe(f)")
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample)


def test_a_premise_admitting_the_pole_keeps_is_pole_safe_falsified_there():
    p = _one(pure_recip, "for x in [-1, 1], assuming x > -0.5, "
                         "is_pole_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "x = 0" in p.counterexample
    assert "ZeroDivisionError" in p.counterexample


def test_a_premise_that_is_not_a_bound_leaves_the_disproof_to_execution():
    # x * x > 0.25 is not an interval on x, so the structural disproof at
    # x = 0 is not reported; the probe finds no admitted pole point
    p = _one(pure_recip, "for x in [-1, 1], assuming x * x > 0.25, "
                         "is_pole_safe(f)")
    assert p.verdict != "falsified", (p.verdict, p.counterexample)


def test_a_premise_that_is_not_a_bound_but_admits_the_pole_still_falsifies():
    p = _one(pure_recip, "for x in [-1, 1], assuming x * x < 0.25, "
                         "is_pole_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ZeroDivisionError" in p.counterexample


@pytest.mark.parametrize("premise", ["x > 0.5", "x >= 0.5"])
def test_the_computation_roll_up_with_a_premise_matches_the_narrow_domain(
        premise):
    narrow = _one(pure_recip, "for x in [0.5, 1], is_computation_safe(f)")
    narrowed = _one(pure_recip, f"for x in [-1, 1], assuming {premise}, "
                                "is_computation_safe(f)")
    assert narrowed.verdict == narrow.verdict, (narrowed.verdict,
                                                narrowed.counterexample)
    assert narrowed.verdict != "falsified"
    assert (narrowed.meta or {}).get("mathema.children") == \
        (narrow.meta or {}).get("mathema.children")
