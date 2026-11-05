# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An equality premise that pins a whole vector or matrix to a value is not
read yet: the claim is unknown on every route, with a note saying so, and no
point is drawn. A premise that relates a value keeps its reading, on every
route and every library: 0 is the zero of the other side's shape, so
`assuming f(x) != 0` says f(x) is not the zero vector. A premise on an element
is an ordinary premise. A claim's own relation stays strict."""
from typing import Optional

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


def m(A: Mat("n", "n")):
    return A


def two_v(x: Vec("n"), y: Vec("n")):
    return x


def form(A: Mat("n", "n"), x: Vec("n")):
    return float(x @ A @ x)


def pd_pair(x: float):
    return pd.Series([x, x])


def pl_pair(x: float):
    return pl.Series([x, x])


def pd_frame(x: float):
    return pd.DataFrame({"a": [x, x]})


def tuple_pair(x: float):
    return (x, x)


def _anyx(x):
    return x


def opt(x: Optional[list[float]]):
    return x


def opt_array(x: Optional[np.ndarray]):
    return x


def det_of(A: np.ndarray) -> float:
    return float(np.linalg.det(np.asarray(A, dtype=float)))


_PINS = [
    (echo, "assuming x == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (echo, "assuming 0 == x, for x in [0,1]^3, f(x) == [0,0,0]"),
    (echo, "assuming x == 0.0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (echo, "assuming x == 5, for x in [0,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming 5 == x, for x in [0,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == -5, for x in [-10,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == [5,5,5], for x in [0,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == [5,5,5], for x in [0,10]^3, f(x) == [6,6,6]"),
    (echo, "assuming x == (5,5,5), for x in [0,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming [5,5,5] == x, for x in [0,10]^3, f(x) == [5,5,5]"),
    (echo, "assuming x == 0 and x[0] >= 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (two_v, "assuming x == 0 and y != 0, x.T @ y == 0"),
    (form, "assuming A is positive definite and x == 0, x.T @ A @ x == 0"),
    (total, "assuming x == 5, for x in [0,10]^3, f(x) == 5"),
    (ndim, "assuming x == 5, for x in [0,10]^3, f(x) == 0"),
    (m, "assuming A == 0, A @ A == A"),
    (m, "assuming A == 5, trace(A) == 5"),
    (m, "assuming A == [[1,0],[0,1]], trace(A) == 2"),
    (det_of, "assuming A == 0, for A in [0,1]^(n,n), f(A) == 0"),
    (elist, "assuming x == 0, for x in [0,1]^3, f(x) == x"),
    (elist, "assuming x == 0, f(x) == x"),
    (opt, "assuming x == 0, for x in [0,1]^3 | {None}, f(x) == [0,0,0]"),
    (opt, "assuming x == 0, f(x) == [0,0,0]"),
    (opt_array, "assuming x == 0, for x in [0,1]^3 | {None}, f(x) == [0,0,0]"),
    (_anyx, "assuming x == 0, for x in [0,1]^2, f(x) == [0,0]"),
    (_anyx, "assuming x == 0, for x in [0,1]^(2,2), f(x) == [[0,0],[0,0]]"),
    (echo, "assuming x == ['a','b'], for x in [0,1]^2, f(x) == x"),
    (echo, "assuming x == [None, 1], for x in [0,1]^2, f(x) == x"),
]


@pytest.mark.parametrize("route", ["best", "probe", "derive"])
@pytest.mark.parametrize("fn,law", _PINS, ids=lambda v: getattr(v, "__name__", v))
def test_a_premise_pinning_a_whole_container_is_not_read_yet(fn, law, route):
    probe = _probe(fn, law, route=route)
    assert probe.verdict == "unknown", (probe.verdict, probe.counterexample)
    assert probe.n == 0
    assert "not read yet" in probe.note, probe.note
    assert remedy_statements(probe.note) == [], probe.note


def test_a_pin_draws_no_point():
    calls = []

    def counted(x):
        calls.append(x)
        return x

    probe = _probe(counted, "assuming x == 0, for x in [0,1]^2, f(x) == [0,0]")
    assert probe.verdict == "unknown"
    assert calls == []


def test_a_pin_shows_where_a_record_is_read():
    import mathema
    record = mathema.check(echo, claims=[mathema.claim(
        "assuming x == 5, for x in [0,10]^3, f(x) == [5,5,5]", name="c")])
    assert "not read yet" in str(record), str(record)


def test_no_draw_pins_a_container():
    for law in ("assuming x == 0, for x in [0,1]^3, f(x)[0] == 0",
                "assuming x == [1,1,1], for x in [0,1]^3, f(x)[0] == 1"):
        cj = claim(law, name="c")
        premises = _interpret_assumption(cj, [cj])[2]
        assert _premises.premise_draws(premises, {"x": "vec"}, cj.domain) == {}
        assert _premises.solve_equality(premises, {"x": "vec"}, cj.domain) is None


@pytest.mark.parametrize("fn,law", [
    (echo, "assuming x != 0, for x in {0,1}^2, f(x)[0] + f(x)[1] > 0"),
    (echo, "assuming x != 5, for x in [0,1]^3, f(x)[0] <= 1"),
    (echo, "assuming x[0] == 0, for x in [0,1]^3, f(x)[0] == 0"),
    (echo, "assuming sum(x) == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (echo, "assuming norm(x) == 0, for x in [0,1]^3, f(x) == [0,0,0]"),
    (echo, "assuming max(x) == min(x), for x in [0,1]^3, f(x)[0] == f(x)[1]"),
    (pair, "assuming f(x) == 0, for x in {0.0, 1.0}, x == 0"),
    (pair, "assuming f(x) != 0, for x in {0.0, 1.0}, x > 0"),
], ids=lambda v: getattr(v, "__name__", v))
def test_a_relation_or_an_element_premise_stays_read(fn, law):
    probe = _probe(fn, law)
    assert probe.verdict in ("holds", "proven"), (probe.verdict, probe.note,
                                                  probe.counterexample)


def _ragged(x: float):
    return [[1.0], [x, 2.0]]


def _ragged_zeros(x: float):
    return [[0.0], [0.0, 0.0]]


@pytest.mark.parametrize("route", ["best", "probe"])
def test_a_ragged_value_in_a_premise_gets_a_verdict(route):
    probe = _probe(_ragged, "assuming f(x) != 0, for x in {0.0, 1.0}, x >= 0",
                   route=route)
    assert probe.verdict in ("holds", "proven", "unknown"), probe.verdict


def test_a_ragged_value_is_not_the_zero():
    assert _probe(_ragged, "assuming f(x) != 0, for x in {0.0, 1.0}, x >= 0"
                  ).verdict in ("holds", "proven")
    assert _probe(_ragged_zeros, "assuming f(x) != 0, for x in {0.0, 1.0}, x >= 0"
                  ).verdict in ("holds", "proven")
    assert _premises.premise_relation([[0.0], [0.0, 0.0]], 0, "==", 1e-9, 0.0) is False
    assert _premises.premise_relation([[0.0], [0.0, 0.0]], 0, "!=", 1e-9, 0.0) is True


def test_a_companion_reads_a_premise_exactly():
    from mathema import gates
    from mathema.conjecture import _effective_facts

    def plain(x: float) -> float:
        return x

    cj = claim("assuming x == 0, for x in [-1, 1], f(x) == 0", name="c")
    facts = _effective_facts(plain, None)
    premise = [("x", "==", "0")]
    tolerant = gates._point_evaluator(cj, plain, facts, cj.domain, {}, premise)
    exact = gates._point_evaluator(cj, plain, facts, cj.domain, {}, premise,
                                   exact_premises=True)
    assert tolerant["admits"]({"x": 1e-10}) is True
    assert exact["admits"]({"x": 1e-10}) is False
    assert exact["admits"]({"x": 0.0}) is True


def test_a_companion_leaves_out_what_a_premise_leaves_out():
    from mathema.conjecture import _outside_premise_shapes
    outside = _outside_premise_shapes(form, {"A": ("is_positive_definite",)})
    good = {"A": [[2.0, 0.0], [0.0, 2.0]], "x": [1.0, 1.0]}
    assert outside(good) is False
    assert outside({**good, "A": [[-1.0, 0.0], [0.0, -1.0]]}) is True
    assert outside({**good, "A": [1.0, 1.0]}) is True


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
