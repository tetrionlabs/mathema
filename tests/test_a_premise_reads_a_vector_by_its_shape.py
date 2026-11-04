# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise over a vector or a matrix never puts a number on it. In a
premise 0 is the zero of the other side's shape on every route, so
`assuming x == 0` draws the zero vector and `assuming f(x) != 0` says
f(x) is not the zero vector. Any other number against a vector admits no
point: the claim has no valid domain, and the note gives the vector.
A claim's own relation stays strict."""
import numpy as np
import pandas as pd
import polars as pl
import pytest

from mathema import _premises
from mathema._missing_words import remedy_statements
from mathema.conjecture import _interpret_assumption, check_conjectures, claim
from mathema.types import Mat, Vec


def echo(x: np.ndarray):
    return np.asarray(x, dtype=float)


def elist(x: list):
    return [float(v) for v in x]


def total(x: np.ndarray) -> float:
    return float(np.sum(x))


def ndim(x: np.ndarray) -> int:
    return int(np.ndim(x))


def pair(x: float):
    return np.array([x, x])


def _probe(fn, law, **kw):
    (probe,) = check_conjectures(fn, [claim(law, name="c", **kw)])
    return probe


@pytest.mark.parametrize("fn,law", [
    (echo, "assuming x == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (elist, "assuming x == 0, for x in [0,1]^3, f(x) == x"),
    (total, "assuming x == 0, for x in [0,1]^3, f(x) == 0"),
    (ndim, "assuming x == 0, for x in [0,1]^3, f(x) == 1"),
])
def test_x_equal_to_0_draws_the_zero_vector_of_its_shape(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


def test_a_matrix_equal_to_0_draws_the_zero_matrix():
    probe = _probe(echo, "assuming x == 0, for x in [0,1]^(2,3), "
                         "f(x) == [[0,0,0],[0,0,0]]")
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


@pytest.mark.parametrize("fn,law", [
    (echo, "assuming x == 5, for x in [0,10]^3, f(x) == [5,5,5]"),
    (total, "assuming x == 5, for x in [0,10]^3, f(x) == 5"),
    (ndim, "assuming x == 5, for x in [0,10]^3, f(x) == 0"),
])
def test_a_number_against_a_vector_admits_no_point(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "unknown", (probe.verdict, probe.counterexample)
    assert probe.n == 0
    assert "no valid domain" in probe.note, probe.note
    assert "x == [5, 5, 5]" in probe.note, probe.note
    corrected = remedy_statements(probe.note)
    assert corrected == [law.replace("x == 5", "x == [5, 5, 5]")], probe.note


def test_the_corrected_vector_premise_is_drawn():
    probe = _probe(echo, "assuming x == [5, 5, 5], for x in [0,10]^3, "
                         "f(x) == [5,5,5]")
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


def test_a_number_against_a_vector_of_open_length_gives_nothing():
    probe = _probe(echo, "assuming x == 5, for x in [0,10]^n, f(x)[0] == 5")
    assert probe.verdict == "unknown", (probe.verdict, probe.counterexample)
    assert "no valid domain" in probe.note, probe.note
    assert remedy_statements(probe.note) == [], probe.note


def test_the_draws_never_hold_a_number_for_a_vector():
    import random
    cj = claim("assuming x == 0, for x in [0,1]^3, f(x) == [0,0,0]", name="c")
    premises = _interpret_assumption(cj, [cj])[2]
    kinds = {"x": "vec"}
    (draw,) = _premises.premise_draws(premises, kinds, cj.domain).values()
    assert _premises.placed_draw(draw, random.Random(0), None,
                                 [1.0, 1.0, 1.0]) == [0.0, 0.0, 0.0]
    assert _premises.solve_equality(premises, kinds) is None


@pytest.mark.parametrize("kw", [{}, {"route": "probe"}, {"route": "derive"}])
def test_0_is_the_zero_of_the_shape_in_a_premise_on_every_route(kw):
    probe = _probe(pair, "assuming f(x) != 0, for x in {0.0, 1.0}, f(x)[0] > 0",
                   **kw)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.route,
                                                  probe.counterexample)


def test_a_premise_equal_to_0_keeps_the_zero_point_on_every_route():
    for kw in ({}, {"route": "probe"}):
        probe = _probe(pair, "assuming f(x) == 0, for x in {0.0, 1.0}, "
                             "f(x)[0] == 0", **kw)
        assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.route,
                                                      probe.counterexample)


def test_every_route_shares_one_premise_reading():
    holds = _premises.premise_relation
    assert holds([0.0, 0.0], 0, "==", 1e-9, 0.0) is True
    assert holds([0.0, 0.0], 0, "!=", 1e-9, 0.0) is False
    assert holds(0, [1.0, 0.0], "!=", 1e-9, 0.0) is True
    assert holds([1.0, 1.0], 1, "==", 1e-9, 0.0) is False
    assert holds([1.0, 1.0], 0, ">", 1e-9, 0.0) is True


def test_a_claim_of_its_own_stays_strict():
    assert _probe(pair, "for x in {0.0}, f(x) == 0").verdict == "falsified"
    assert _probe(pair, "for x in {0.0}, f(x) != 0").verdict in ("holds", "proven")


def test_no_valid_domain_shows_where_a_record_is_read():
    import mathema
    record = mathema.check(echo, claims=[mathema.claim(
        "assuming x == 5, for x in [0,10]^3, f(x) == [5,5,5]", name="c")])
    assert "no valid domain" in str(record), str(record)
    assert "x == [5, 5, 5]" in str(record), str(record)


def m(A: Mat("n", "n")):
    return A


def det_of(A: np.ndarray) -> float:
    return float(np.linalg.det(np.asarray(A, dtype=float)))


def two_v(x: Vec("n"), y: Vec("n")):
    return x


def form(A: Mat("n", "n"), x: Vec("n")):
    return float(x @ A @ x)


def scal(x: float) -> float:
    return x + 1.0


def dot(xs: list[float], ys: list[float]) -> float:
    return sum(a * b for a, b in zip(xs, ys))


def pd_pair(x: float):
    return pd.Series([x, x])


def pl_pair(x: float):
    return pl.Series([x, x])


def pd_frame(x: float):
    return pd.DataFrame({"a": [x, x]})


def tuple_pair(x: float):
    return (x, x)


@pytest.mark.parametrize("fn,law", [
    (echo, "assuming x == 0, for x in [1,2]^3, f(x) == [0,0,0]"),
    (echo, "assuming x == 0, for x in [1,2]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == [5,5,5], for x in [0,1]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == [5,5,5], for x in [0,1]^3, f(x) == [6,6,6]"),
    (echo, "assuming x == [1,1], for x in [0,1]^3, f(x) == [1,1]"),
    (echo, "assuming x == [[1,1],[1]], for x in [0,1]^(n,n), f(x)[0][0] == 1"),
    (echo, "assuming x == [[1,1,1],[1,1,1]], for x in [0,1]^(n,n), f(x)[0][0] == 1"),
    (scal, "assuming x == [1,2], for x in [0,5], f(x) == 3"),
    (elist, "assuming x == 0, for x in {1,2}^2, f(x) == [5,5]"),
])
def test_a_premise_the_domain_excludes_has_no_valid_domain(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict == "unknown", (probe.verdict, probe.counterexample)
    assert "no valid domain" in probe.note, probe.note
    assert remedy_statements(probe.note) == [], probe.note


def test_the_pin_is_not_given_outside_the_domain():
    probe = _probe(echo, "assuming x == 5, for x in [0,1]^3, f(x) == [5,5,5]")
    assert probe.verdict == "unknown"
    assert remedy_statements(probe.note) == [], probe.note
    assert "excludes 5" in probe.note, probe.note


def test_a_literal_draw_ties_every_dimension_it_shares():
    law = ("assuming xs == [1,1,1], for xs in [-1,1]^n, ys in [-1,1]^n, "
           "f(xs, ys) == ys[0]+ys[1]+ys[2]")
    probe = _probe(dot, law)
    assert probe.verdict in ("holds", "proven", "unknown"), (
        probe.verdict, probe.counterexample)


@pytest.mark.parametrize("fn,law", [
    (det_of, "assuming A == 0, for A in [0,1]^(n,n), f(A) == 0"),
    (det_of, "assuming A == 0, for A in [0,1]^(2,2), f(A) == 0"),
    (m, "assuming A == 0, A @ A == A"),
    (m, "assuming A == 0, trace(A) == 0"),
    (m, "assuming A == 0, for A in R^(n,n), A @ A == A"),
])
def test_the_zero_of_a_matrix_has_the_matrix_shape(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


@pytest.mark.parametrize("fn,law", [
    (two_v, "assuming x == 0, x.T @ y == 0"),
    (form, "assuming A is positive definite and x == 0, x.T @ A @ x == 0"),
])
def test_a_companion_counts_only_points_inside_the_premise(fn, law):
    rows = check_conjectures(fn, [claim(law, name="c")], float_companions=True)
    (row, *companions) = rows
    assert row.verdict in ("holds", "proven"), (row.verdict, row.counterexample)
    for line in companions:
        assert line.verdict != "falsified", (line.name, line.counterexample)


def test_the_zero_reading_reaches_a_tuple_on_the_probe_route():
    probe = _probe(tuple_pair, "assuming f(x) != 0, for x in {0.0, 1.0}, x > 0",
                   route="probe")
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.counterexample)


@pytest.mark.parametrize("fn", [pd_pair, pl_pair, pd_frame, pair])
@pytest.mark.parametrize("kw", [{}, {"route": "probe"}])
def test_the_zero_reading_reaches_every_library(fn, kw):
    probe = _probe(fn, "assuming f(x) != 0, for x in {0.0, 1.0}, x > 0", **kw)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.route,
                                                  probe.counterexample)
    probe = _probe(fn, "assuming f(x) == 0, for x in {0.0, 1.0}, x == 0", **kw)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.route,
                                                  probe.counterexample)


@pytest.mark.parametrize("law", [
    "for A in [0,1]^(1,1), A - A == 0",
    "for A in [0,1]^(1,1), A - A ~= 0",
    "for x in [0,1]^1, x - x == 0",
])
def test_a_size_one_array_is_not_a_number_in_the_algebra(law):
    probe = _probe(m if "A" in law else elist, law)
    assert probe.verdict == "falsified", (probe.verdict, probe.route, probe.sketch)


@pytest.mark.parametrize("law", [
    "for A in [0,1]^(1,1), A - A == [[0]]",
    "for A in [0,1]^(1,1), A == A",
])
def test_a_size_one_array_still_meets_an_array(law):
    assert _probe(m, law).verdict in ("holds", "proven")


def test_a_quadratic_form_at_size_one_is_still_a_number():
    probe = _probe(form, "assuming A is positive definite, "
                         "for A in R^(1,1), x in R^1, x.T @ A @ x == x.T @ (A @ x)")
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.sketch)


def test_a_family_guard_places_a_draw_by_the_points_own_shape():
    import random
    zero = _premises._ZeroOfShape()
    assert _premises.placed_draw(zero, random.Random(0), None,
                                 [[1.0, 2.0], [3.0, 4.0]]) == [[0.0, 0.0], [0.0, 0.0]]
    literal = _premises._LiteralVector([1, 1])
    assert _premises.placed_draw(literal, random.Random(0), None, [0.0, 0.0]) == [1, 1]
    assert _premises.placed_draw(literal, random.Random(0), None,
                                 [0.0, 0.0, 0.0]) is _premises.NO_POINT


def test_a_matrix_premise_says_matrix():
    probe = _probe(m, "assuming A == 5, trace(A) == 5")
    assert probe.verdict == "unknown"
    assert "the matrix A" in probe.note, probe.note
