# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Sequence draws include the corners where float arithmetic breaks:
entries that cancel at a large magnitude ([1e16, -1e16]), entries near
the largest double, and a nearly constant series one ulp from
constant, the cases a uniform draw almost never makes. A draw that
passes only within the tolerance there is decided in exact arithmetic
(rulings of 2026-10-01 and 2026-10-05: the corners are turned on with
the strata work, the mathematics is exact, tolerance belongs to the
computation)."""
import math

import numpy as np

from mathema.conjecture import check_conjectures, claim


def running_total(xs: list, y0: float) -> float:
    y = y0
    for v in xs:
        y = y + v
    return y


def middle(xs: np.ndarray) -> float:
    return float(np.percentile(xs, 50))


def signal_to_noise(xs: list) -> float:
    m = sum(xs) / len(xs)
    var = sum((v - m) ** 2 for v in xs) / (len(xs) - 1)
    return m / math.sqrt(var)


def test_a_cancelling_pair_is_drawn_and_decided_exactly():
    # the shift is exact mathematics; at [1e16, -1e16, ...] the float
    # sum is off by 1, which passes within that draw's round-off only
    # because the code run on exact numbers satisfies the claim there
    (p,) = check_conjectures(running_total, [claim(
        "for xs in R^n, y0 in [-10, 10], f(xs, y0 + 1) == f(xs, y0) + 1",
        route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note)
    assert "at xs = [1e+16, -1e+16" in p.note, p.note


def test_entries_near_the_float_limit_break_a_range_claim():
    (p,) = check_conjectures(middle, [claim(
        "for xs in [-1.7e308, 1.7e308]^n, min(xs) <= f(xs) <= max(xs)",
        route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_nearly_constant_series_meets_a_std_premise():
    # a series one ulp from constant passes `std > 0` and has an
    # enormous mean-to-deviation ratio; the square root keeps it from
    # being evaluated exactly, so those draws are inconclusive
    (p,) = check_conjectures(signal_to_noise, [claim(
        "for xs in [0.5, 1]^n, assuming n >= 2 and std(xs, ddof=1) > 0, "
        "abs(f(xs)) <= 1e9", route="probe")])
    assert p.verdict != "falsified", (p.verdict, p.counterexample)
    assert "could not be evaluated in exact arithmetic" in p.note, p.note


def test_every_corner_entry_lies_in_the_element_range():
    import random

    from mathema.probing import _sequence_corner
    bounds = (1e307, 1.7e308)
    rng = random.Random(0)
    for _ in range(400):
        corner = _sequence_corner(rng, 5, bounds)
        assert corner is not None
        assert all(1e307 <= v <= 1.7e308 for v in corner), corner


def scaled_total(xs: list, c: float) -> float:
    y = 0.0
    for v in xs:
        y = y + c * v
    return y


def test_the_float_limit_pair_is_drawn_for_an_unbounded_sequence():
    # the interpolation between -M and M at the largest double
    # overflows, a pair a uniform draw over R^n never makes: it is a
    # corner every sequence parameter meets, not a chance draw
    (p,) = check_conjectures(middle, [claim(
        "for xs in R^n, min(xs) <= f(xs) <= max(xs)", route="probe")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "e+308" in p.counterexample, p.counterexample


def test_the_corners_are_the_pairs_of_the_element_range():
    from mathema._sampling import representation_reach
    from mathema.probing import sequence_corners
    reach = representation_reach()
    assert sequence_corners(None) == [[1e16, -1e16], [1e300, -1e300],
                                      [reach, -reach]]
    assert sequence_corners((-1e308, 1e308), 3) == [
        [1e16, -1e16, 1e16], [1e300, -1e300, 1e300], [1e308, -1e308, 1e308]]
    assert sequence_corners((0.5, 1)) == [[0.5, 1]]
    assert sequence_corners((1e307, 1.7e308), 1) == []


def test_a_proven_claims_computation_line_runs_the_float_limit_pair():
    # 2 * M overflows at the largest double M: the computation line of a
    # proven claim meets the pair whatever the random draws do
    import mathema
    rows = {p.name: p for p in mathema.check(scaled_total, claims=[
        "for xs in R^n, c in [2, 3], f(xs, c) == c * f(xs, 1)"]).probes}
    (main,) = [p for name, p in rows.items() if "[" not in name
               and name.startswith("f_xs")]
    assert main.verdict == "proven", (main.verdict, main.note)
    companion = rows[f"{main.name}[float]"]
    assert companion.verdict == "falsified", (companion.verdict, companion.note)
    assert "e+308" in companion.counterexample, companion.counterexample


# the float limit pair breaks each kind of carrier in the same way: the
# scaled or solved values overflow where the exact ones are finite

def scale_array(returns: np.ndarray, c: float):
    return returns * c


def scale_series(returns, c: float):
    return returns * c


def scale_column(df, c: float):
    return df["returns"] * c


def solve_for(A: np.ndarray, b: np.ndarray):
    return np.linalg.solve(A, b)


def _falsified_at_the_limit(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    assert p.verdict == "falsified", (law, p.verdict, p.note)
    assert "e+308" in (p.counterexample or ""), p.counterexample
    return p


def test_a_scaled_vector_meets_the_float_limit_pair():
    _falsified_at_the_limit(
        scale_array, "for returns in R^n, c in [-2, 2], f(returns, c) == c * returns")


def test_a_scaled_series_meets_the_float_limit_pair():
    pd = __import__("pytest").importorskip("pandas")
    scale_series.__annotations__["returns"] = pd.Series
    _falsified_at_the_limit(
        scale_series, "for returns in R^n, c in [-2, 2], f(returns, c) == c * returns")


def test_a_scaled_table_column_meets_the_float_limit_pair():
    pd = __import__("pytest").importorskip("pandas")
    scale_column.__annotations__["df"] = pd.DataFrame
    _falsified_at_the_limit(
        scale_column, "for c in [-2, 2], f(df, c) == c * df.returns")


def test_a_solved_system_meets_the_float_limit_pair():
    _falsified_at_the_limit(
        solve_for,
        "for A in R^(n,n), b in R^n, assuming det(A) != 0, A @ f(A, b) == b")
