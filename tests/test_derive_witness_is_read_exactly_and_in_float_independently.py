# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Derive's witness has two independent readings: the code's float run
at the point, and the exact reading of the point (each coordinate as
written, the body read exactly). Both run at every point. The exact
reading decides the mathematics; a float run with no value there (a
raise in the claim's own plumbing) leaves the exact reading to decide.
Where the two readings disagree, the note says so: the float run holds
at the point while the exact reading makes the claim false.
"""
from fractions import Fraction

from mathema import gates
from mathema.conjecture import check_conjectures, claim


def nudged_by_a_literal(x: float) -> float:
    return x + 1e-17


class _Readings:
    """A point evaluator whose float run and exact reading are given,
    recording the order in which they run."""

    def __init__(self, float_held, exact_sides):
        self.float_held = float_held
        self.exact_sides = exact_sides
        self.order: list = []

    def __call__(self, point):
        self.order.append("float")
        return self.float_held

    def sides(self):
        return (1.0, 1.0) if self.float_held is not None else None

    def exact_as_written(self, point):
        self.order.append("exact")
        return self.exact_sides


def _reading(evaluator, relation="=="):
    cj = claim(f"f(x) {relation} x")
    return gates._exact_reading(cj, {"evaluate": evaluator}, {}, {"x": 1.0},
                                "mathematics")


def test_both_readings_run_and_the_float_run_comes_first():
    evaluator = _Readings(True, (Fraction(1), Fraction(1)))
    held, _record, _disagreement = _reading(evaluator)
    assert held is True
    assert evaluator.order == ["float", "exact"]


def test_a_float_run_with_no_value_leaves_the_exact_reading_to_decide():
    evaluator = _Readings(None, (Fraction(1), Fraction(2)))
    held, record, disagreement = _reading(evaluator)
    assert held is False
    assert record["reading"] == "mathematics"
    assert disagreement is None
    assert evaluator.order == ["float", "exact"]


def test_the_float_run_runs_where_the_exact_reading_has_no_value():
    evaluator = _Readings(False, None)
    held, record, disagreement = _reading(evaluator)
    assert (held, record, disagreement) == (None, None, None)
    assert evaluator.order == ["float", "exact"]


def test_a_disagreement_between_the_readings_is_returned():
    evaluator = _Readings(True, (Fraction(1), Fraction(2)))
    held, _record, disagreement = _reading(evaluator)
    assert held is False
    assert disagreement and "float run" in disagreement, disagreement


def test_the_readings_that_agree_report_no_disagreement():
    evaluator = _Readings(False, (Fraction(1), Fraction(2)))
    assert _reading(evaluator)[2] is None


def test_the_note_reports_where_the_two_readings_disagree():
    (p,) = check_conjectures(nudged_by_a_literal,
                             [claim("for x in [1, 2], f(x) == x")])
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert p.meta["mathema.exact_witness"]["reading"] == "mathematics"
    assert "the two readings of derive's witness disagree" in p.note, p.note
