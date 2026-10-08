# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_defined` is proven only when the region it names is the whole
region where the body has a value. A call whose definedness mathema
does not know (a method on a series, an uncatalogued helper), or a
region with no expressible complement (gamma's poles), leaves that
region unknown: the claim is then decided by execution, never proven
from the part of the region that is known."""
import pytest

pytest.importorskip("numpy")
pytest.importorskip("pandas")

import math  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402


def log_and_gamma(x: float) -> float:
    return math.log(x + 3) + math.gamma(x)


def float64_reciprocal(x: float) -> float:
    return 1 / np.float64(x)


def _helper(x):
    return 1.0 / x


def calls_a_helper(x: float) -> float:
    return _helper(x) + 1.0


def ratio(returns: pd.Series) -> float:
    return returns.mean() / returns.std(ddof=1)


@pytest.mark.needs_full_proof_budget
def test_a_restriction_naming_part_of_the_region_is_not_proven():
    # log(x + 3) needs x > -3, gamma(x) has no value at 0, -1 and -2
    (p,) = check_conjectures(log_and_gamma, [
        claim("x + 3 > 0", name="is_defined", route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)


@pytest.mark.needs_full_proof_budget
def test_a_restriction_is_falsified_where_the_region_it_misses_is_executed():
    (p,) = check_conjectures(log_and_gamma, [
        claim("for x in [-2, 2], x + 3 > 0", name="is_defined",
              route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn", [float64_reciprocal, calls_a_helper])
def test_bare_is_defined_over_a_call_of_unknown_definedness(fn):
    (p,) = check_conjectures(fn, [
        claim("for x in [-2, 2], is_defined(f)", route="derive")])
    assert p.verdict != "proven", (fn.__name__, p.verdict, p.sketch)
    (p,) = check_conjectures(fn, [
        claim("for x in [-2, 2], is_defined(f)", route="best")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.sketch)


@pytest.mark.needs_full_proof_budget
@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_a_ratio_over_a_spread_is_not_defined_on_a_constant_series():
    # a constant series has a zero sample deviation, a single one none
    assert not math.isfinite(ratio(pd.Series([0.05, 0.05])))
    (p,) = check_conjectures(ratio, [
        claim("for returns in [-0.1, 0.1]^n, is_defined(f)",
              route="derive")])
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)
    (p,) = check_conjectures(ratio, [
        claim("for returns in [-0.1, 0.1]^n, is_defined(f)")])
    assert p.verdict != "proven", (p.verdict, p.sketch, p.note)


def test_a_total_body_is_still_proven_defined():
    def smooth(x: float) -> float:
        return math.exp(x) + math.sin(x) * abs(x)

    (p,) = check_conjectures(smooth, [
        claim("for x in [-2, 2], is_defined(f)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
