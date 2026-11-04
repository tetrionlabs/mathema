# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A premise over a vector or a matrix never puts a number on it. In a
premise 0 is the zero of the other side's shape on every route, so
`assuming x == 0` draws the zero vector and `assuming f(x) != 0` says
f(x) is not the zero vector. Any other number against a vector admits no
point: the claim has no valid domain, and the note offers the vector.
A claim's own relation stays strict."""
import numpy as np
import pytest

from mathema import _premises
from mathema._missing_words import remedy_statements
from mathema.conjecture import _interpret_assumption, check_conjectures, claim


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
    offered = remedy_statements(probe.note)
    assert offered == [law.replace("x == 5", "x == [5, 5, 5]")], probe.note


def test_the_offered_vector_premise_is_drawn():
    probe = _probe(echo, "assuming x == [5, 5, 5], for x in [0,10]^3, "
                         "f(x) == [5,5,5]")
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


def test_a_number_against_a_vector_of_open_length_offers_nothing():
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
    assert draw(random.Random(0), None) == [0.0, 0.0, 0.0]
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
