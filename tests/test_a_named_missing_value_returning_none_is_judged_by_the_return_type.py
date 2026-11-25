# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Where the function returns None or nan at a named missing value, its
return annotation judges the result: a return type that does not admit
it falsifies, with that point as the witness. A None it admits (or no
annotation) leaves the point out of the claim's printed domain, the
proof over the rest stands, and the note says what was returned; a nan
it admits is left out the same way."""
import math
from typing import Optional

import pytest

from mathema.conjecture import check_conjectures, claim

TEXT = "for x in {1, None}, y in [0, 1], f(x, y) == 0"


def none_under_float(x: Optional[float], y: float) -> float:
    if x is None:
        return None  # type: ignore[return-value]
    return (x - 1) * y


def none_under_optional(x: Optional[float], y: float) -> "float | None":
    if x is None:
        return None
    return (x - 1) * y


def none_unannotated(x: Optional[float], y: float):
    if x is None:
        return None
    return (x - 1) * y


def root(x: float) -> float:
    return math.sqrt(x)


def _row(fn, text):
    (row,) = check_conjectures(fn, [claim(text)])
    return row


@pytest.mark.needs_smt
@pytest.mark.needs_full_proof_budget
def test_none_under_a_float_return_falsifies():
    row = _row(none_under_float, TEXT)
    assert row.verdict == "falsified", (row.verdict, row.route, row.note)
    assert row.counterexample.startswith("x = None"), row.counterexample
    assert "return type float does not admit" in (row.sketch or ""), row.sketch


@pytest.mark.needs_smt
@pytest.mark.needs_full_proof_budget
def test_none_under_an_optional_return_leaves_the_point_out():
    row = _row(none_under_optional, TEXT)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "absent" not in row.statement, row.statement
    assert "x = None is left out of the domain: f returned None there" in row.note, \
        row.note


@pytest.mark.needs_smt
@pytest.mark.needs_full_proof_budget
def test_none_with_no_return_annotation_leaves_the_point_out():
    row = _row(none_unannotated, TEXT)
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "absent" not in row.statement, row.statement


def nan_at_none(x: Optional[float]) -> float:
    if x is None:
        return math.nan
    return x


def test_a_propagated_nan_under_a_float_return_is_left_out_of_the_domain():
    row = _row(root, "for x in [0, 1] | {nan}, f(x) >= 0")
    assert row.verdict == "proven", (row.verdict, row.route, row.note)
    assert "nan" not in row.statement, row.statement
    assert ("x = nan is left out of the domain: f returned nan there, which its "
            "return type float admits") in (row.note or ""), row.note


@pytest.mark.parametrize("domain, restated", [
    ("[0, 1] | {None}", "for x in [0.0, 1.0] : float|absent|missing, f(x) >= 0"),
    ("{0.5, 1, None}", "for x in {0.5, 1}, f(x) >= 0"),
    ("[0, 1] : float|absent", "for x in [0.0, 1.0] : float, f(x) >= 0")])
def test_a_nan_returned_at_a_named_none_is_left_out_of_the_domain(domain, restated):
    row = _row(nan_at_none, f"for x in {domain}, f(x) >= 0")
    assert row.verdict in ("proven", "holds"), (row.verdict, row.route, row.note)
    assert row.statement == restated, row.statement
    assert "x = None is left out of the domain: f returned nan there" in (row.note or ""), \
        row.note
