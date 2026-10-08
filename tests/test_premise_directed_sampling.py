# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An equality premise random draws would essentially never satisfy is
sampled directly: `dim(a) == 0` draws the empty sequence, `dim(a) == k`
draws length k, `det(a) == 0` draws singular matrices, and `x == c`
draws c. A premise nothing can construct still skips with "no sampled
point satisfied the assuming clause"."""
import random

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim
from mathema.matrices import _synth_singular


def head(xs):
    return xs[0]


def _declared(fn, statement):
    (p,) = [p for p in mathema.check(fn, claims=[statement]).probes
            if p.meta.get("mathema.surface") == "declared"]
    return p


def test_an_empty_sequence_premise_draws_the_empty_sequence():
    (p,) = check_conjectures(head, [claim(
        "for xs in R^n, assuming dim(xs) == 0, raises(f(xs), IndexError)",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_length_premise_draws_that_length():
    (p,) = check_conjectures(head, [claim(
        "for xs in R^n, assuming dim(xs) == 3, f(xs) == xs[0]",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_statistics_mean_raises_on_the_empty_sequence():
    import statistics
    p = _declared(statistics.mean, "for data in R^n, assuming dim(data) == 0, "
                                   "raises(f(data), StatisticsError)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_numpy_inv_raises_on_a_singular_matrix():
    np = pytest.importorskip("numpy")
    p = _declared(np.linalg.inv, "for a in R^(n,n), assuming det(a) == 0, "
                                 "raises(f(a), LinAlgError)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_scalar_equality_premise_draws_the_constant():
    def shifted(x: float) -> float:
        return x - 2.0

    (p,) = check_conjectures(shifted, [claim(
        "for x in [0, 5], assuming x == 2, f(x) == 0", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_premise_nothing_constructs_still_skips():
    (p,) = check_conjectures(head, [claim(
        "for xs in R^n, assuming xs[0] == 0.12345, f(xs) >= 0",
        route="probe")])
    assert p.verdict == "skipped"
    assert "no sampled point satisfied the assuming clause" in p.note


@pytest.mark.parametrize("n", [1, 2, 3, 5])
def test_synth_singular_is_singular(n):
    np = pytest.importorskip("numpy")
    rng = random.Random(n)
    for _ in range(20):
        m = _synth_singular(n, rng)
        assert len(m) == n and all(len(row) == n for row in m)
        with pytest.raises(np.linalg.LinAlgError):
            np.linalg.inv(np.asarray(m))
