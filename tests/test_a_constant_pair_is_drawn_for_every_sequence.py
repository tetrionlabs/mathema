# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The definedness probe draws every sequence parameter, a list or a
pandas Series alike, at the constant pair: two equal elements, where a
spread is zero and a ratio over it has no value."""
import re

import pytest

from mathema.conjecture import check_conjectures, claim

pd = pytest.importorskip("pandas")


def flat_series(s: pd.Series) -> float:
    # no value where the first two elements are equal
    if len(s) < 2:
        return 0.0
    return 1.0 / (s.iloc[0] - s.iloc[1])


def flat_list(s: list) -> float:
    if len(s) < 2:
        return 0.0
    return 1.0 / (s[0] - s[1])


def ratio(returns: pd.Series) -> float:
    return returns.mean() / returns.std(ddof=1)


@pytest.mark.parametrize("fn", [flat_series, flat_list])
def test_the_constant_pair_is_drawn(fn):
    (p,) = check_conjectures(fn, [claim("for s in [-0.1, 0.1]^n, is_defined(f)")])
    assert p.verdict == "falsified", (fn.__name__, p.verdict, p.note)
    # the witness is the constant draw: every element equal, inside the
    # range, not at its ends
    values = [float(v) for v in re.findall(r"-?\d\.\d+(?:e-?\d+)?",
                                           p.counterexample.split("]")[0])]
    assert len(values) >= 2 and len(set(values)) == 1, p.counterexample
    assert -0.1 < values[0] < 0.1, p.counterexample


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_a_single_element_spread_stays_undecidable():
    # std(ddof=1) of one element is nan with no numpy flag, and the body
    # cannot be read exactly: that point decides nothing
    (p,) = check_conjectures(ratio, [claim(
        "assuming dim(returns) == 1, for returns in [-0.1, 0.1]^n, is_defined(f)")])
    assert p.verdict == "unknown", (p.verdict, p.counterexample, p.note)
