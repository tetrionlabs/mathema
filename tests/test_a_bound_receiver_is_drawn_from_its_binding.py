# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A method's receiver the claim binds itself (`for self in R^n`) is drawn
from that binding, realised as its runtime type, never built empty by
its class's constructor: `R^n` is never empty, and a witness never lies
outside its parameter's binding."""
import pytest

from mathema.conjecture import check_conjectures, claim

pd = pytest.importorskip("pandas")

def test_a_bound_series_receiver_is_drawn_from_r_n():
    (p,) = check_conjectures(pd.Series.corr, [claim(
        "for self in R^n, other in R^n, abs(f(self, other)) <= 1 + 1e-9",
        route="probe")])
    witness = p.counterexample or ""
    assert "Series([]" not in witness, witness
    assert "dtype: object" not in witness, witness


def test_a_bound_series_receiver_meets_the_premise_it_is_drawn_under():
    (p,) = check_conjectures(pd.Series.corr, [claim(
        "for self in R^n, other in R^n, assuming dim(self) == dim(other) "
        "and dim(self) >= 3, abs(f(self, other)) <= 1 + 1e-9",
        route="probe")])
    witness = p.counterexample or ""
    if p.verdict == "falsified":
        drawn = witness.split("self = ", 1)[1].split("], ", 1)[0]
        assert drawn.startswith("[") and drawn.count(",") >= 2, witness
    assert "Series([]" not in witness, witness


class Box:
    def __init__(self, w: float = 1.0):
        self.w = w

    def area(self) -> float:
        return self.w * self.w


def test_a_bound_user_receiver_is_drawn_from_its_language():
    (p,) = check_conjectures(Box.area, [claim(
        "for self.w in [2, 3], f(self) >= 4", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample)
