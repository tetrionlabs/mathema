# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A `return a, b` body: lift()/lift_conditioned() lift it to a plain
Python tuple of sympy expressions (see Lifted's docstring in symbolic.py)
rather than refusing outright. Claim laws can compare a tuple-valued
f(...) against a tuple literal elementwise, or index a single element."""
import math

from mathema.conjecture import claim, check_conjectures


def to_cartesian(r: float, theta: float) -> tuple:
    return r * math.cos(theta), r * math.sin(theta)


def midpoint(x: float, y: float):
    return (x + y) / 2, x - y


def signed_pair(x: float) -> tuple:
    if x >= 0:
        return x, 1.0
    return -x, -1.0


def test_tuple_equals_tuple_literal_when_both_elements_match():
    results = check_conjectures(
        to_cartesian,
        [claim("f(r, theta) == (r * cos(theta), r * sin(theta))", route="derive")])
    assert results[0].verdict == "proven"


def test_tuple_falsified_when_one_element_is_wrong():
    results = check_conjectures(
        to_cartesian,
        [claim("f(r, theta) == (r * sin(theta), r * cos(theta))", route="derive")])
    assert results[0].verdict == "falsified"


def test_indexing_a_single_tuple_element():
    results = check_conjectures(
        to_cartesian, [claim("f(r, theta)[0] == r * cos(theta)", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        to_cartesian, [claim("f(r, theta)[1] == r * sin(theta)", route="derive")])
    assert results[0].verdict == "proven"


def test_second_tuple_returning_function_also_lifts():
    results = check_conjectures(
        midpoint, [claim("f(x, y)[0] == (x + y) / 2", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        midpoint, [claim("f(x, y)[1] == x - y", route="derive")])
    assert results[0].verdict == "proven"


def test_comparing_a_tuple_valued_claim_against_a_scalar_is_unliftable():
    # not a crash, a clear, reported refusal
    results = check_conjectures(
        to_cartesian, [claim("f(r, theta) == r", route="derive")])
    # the refusal is clear (kept in the note), and the probe fallback
    # then compares the tuple against the scalar for real, which is
    # simply unequal
    assert results[0].verdict == "falsified"
    assert "tuple-valued" in results[0].note


def test_out_of_range_tuple_index_is_unliftable_not_a_crash():
    results = check_conjectures(
        to_cartesian, [claim("f(r, theta)[2] == r", route="derive")])
    assert results[0].verdict == "unknown"


def test_tuple_return_combines_with_domain_conditioned_branch_pruning():
    # branch pruning and tuple returns are independent features; confirms
    # they compose rather than only being tested in isolation
    results = check_conjectures(
        signed_pair, [claim("for x in [0, 10], f(x) == (x, 1.0)", route="derive")])
    assert results[0].verdict == "proven"

    results = check_conjectures(
        signed_pair, [claim("for x in [-10, -1], f(x) == (-x, -1.0)", route="derive")])
    assert results[0].verdict == "proven"
