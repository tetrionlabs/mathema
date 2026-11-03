# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim compares what the function returned with what the claim
wrote. A number and a container are different shapes, so they are unequal,
whichever side each is on. The number 0 is the one exception: it is the
zero of every shape, so `x == 0` says x is the zero vector. An empty
container has no elements, and nothing over no elements decides a verdict:
it equals only another empty container, and an ordering over it has no
answer."""
import numpy as np
import pytest

from mathema import claims
from mathema._allowance import _exactly_equal, float_miss, relation_within
from mathema.conjecture import claim
from mathema.probing import relation_holds_elementwise, values_agree


def _empty(x):
    return []


def _empty_tuple(x):
    return ()


def _empty_array(x):
    return np.array([])


def _nested_empties(x):
    return [[], []]


def _five(x):
    return 5.0


def _text(x):
    return ""


def _fives(x):
    return [5.0, 5.0]


def _five_array(x):
    return np.array([5.0, 5.0])


def _zeros(x):
    return [0.0, 0.0]


def _verdict(fn, law):
    (probe,) = claims.check_conjectures(fn, [claim(law, name="c")])
    return probe.verdict




_MISMATCHES = [
    (_five, "[]"), (_text, "[]"), (_empty, "0"), (_empty, "5"),
    (_empty_tuple, "0"), (_empty_array, "0"), (_empty_array, "5"),
    (_nested_empties, "0"), (_nested_empties, "5"),
    (_nested_empties, "[5.0, 5.0]"), (_fives, "5"), (_five_array, "5"),
    (_five, "[5.0, 5.0]"), (_fives, "[]"), (_empty, "[5.0, 5.0]"),
]
_RELATIONS = ["==", "~="]
_WHERE = [("", "[]"), ("for x in {1, 2}, ", "x"), ("for x in [0, 1], ", "x")]


@pytest.mark.parametrize("relation", _RELATIONS)
@pytest.mark.parametrize("prefix,arg", _WHERE,
                         ids=["ground", "finite-sweep", "probe"])
@pytest.mark.parametrize("fn,written", _MISMATCHES,
                         ids=lambda v: getattr(v, "__name__", str(v)))
def test_a_shape_mismatch_is_falsified(fn, written, prefix, arg, relation):
    law = f"{prefix}f({arg}) {relation} {written}"
    assert _verdict(fn, law) == "falsified"


@pytest.mark.parametrize("fn,written,expected", [
    (_empty, "[]", "proven"),
    (_empty_array, "[]", "proven"),
    (_empty_tuple, "[]", "proven"),
    (_five, "5", "proven"),
    (_fives, "[5.0, 5.0]", "proven"),
    (_five_array, "[5.0, 5.0]", "proven"),
    (_zeros, "[0, 0]", "proven"),
    (_zeros, "0", "proven"),
], ids=lambda v: getattr(v, "__name__", str(v)))
@pytest.mark.parametrize("relation", _RELATIONS)
def test_the_same_shape_is_compared(fn, written, expected, relation):
    assert _verdict(fn, f"f([]) {relation} {written}") == expected


@pytest.mark.parametrize("fn,written", [
    (_five, "[]"), (_text, "[]"), (_empty, "0"), (_empty, "5"),
    (_fives, "5"), (_five, "[5.0, 5.0]"), (_nested_empties, "0"),
], ids=lambda v: getattr(v, "__name__", str(v)))
def test_a_shape_mismatch_satisfies_not_equal(fn, written):
    assert _verdict(fn, f"f([]) != {written}") == "proven"


@pytest.mark.parametrize("fn,written", [
    (_empty, "[]"), (_zeros, "0"), (_zeros, "[0, 0]"), (_five, "5"),
], ids=lambda v: getattr(v, "__name__", str(v)))
def test_equal_values_fail_not_equal(fn, written):
    assert _verdict(fn, f"f([]) != {written}") == "falsified"


@pytest.mark.parametrize("fn,written", [
    (_five, "[]"), (_empty, "5"), (_empty, "[]"), (_empty_array, "5"),
    (_nested_empties, "5"), (_text, "[]"), (_five, "[[], []]"),
], ids=lambda v: getattr(v, "__name__", str(v)))
@pytest.mark.parametrize("relation", ["<=", ">=", "<", ">"])
def test_an_ordering_over_no_elements_has_no_answer(fn, written, relation):
    assert _verdict(fn, f"f([]) {relation} {written}") == "unknown"


def test_an_ordering_still_holds_at_every_element():
    assert _verdict(_fives, "f([]) <= 5") == "proven"
    assert _verdict(_fives, "f([]) < 5") == "falsified"
    assert _verdict(_five, "f([]) >= [5.0, 5.0]") == "proven"


_PAIRS = [
    (5.0, []), ([], 5.0), (0, []), ([], 0), ("", []), ([], ""),
    ([[], []], 0), (0, [[], []]), ([[], []], 5), ([5.0, 5.0], 5),
    (5, [5.0, 5.0]), ([[5.0], [5.0]], 5), (None, []), ([], None),
    (np.array([]), 0), (0, np.array([])), (np.array([5.0, 5.0]), 5),
    (5, np.array([5.0, 5.0])), ([1, 2], [1, 2, 3]), ([], [1]),
    ([[1], []], [[1], [2]]),
]


@pytest.mark.parametrize("lv,rv", _PAIRS, ids=repr)
@pytest.mark.parametrize("relation", _RELATIONS)
def test_every_comparison_reads_a_mismatch_as_unequal(lv, rv, relation):
    assert relation_within(lv, rv, relation) is False
    assert relation_holds_elementwise(lv, rv, relation, 1e-9) is False
    assert not values_agree(lv, rv, broadcast=True)


@pytest.mark.parametrize("lv,rv", _PAIRS, ids=repr)
def test_every_comparison_reads_a_mismatch_as_different(lv, rv):
    assert relation_within(lv, rv, "!=") is True
    assert relation_within(lv, rv, "!=", exact_inequality=False) is True
    assert relation_holds_elementwise(lv, rv, "!=", 1e-9) is True
    assert not _exactly_equal(np.asarray(lv, dtype=object).tolist()
                              if isinstance(lv, np.ndarray) else lv,
                              np.asarray(rv, dtype=object).tolist()
                              if isinstance(rv, np.ndarray) else rv)


@pytest.mark.parametrize("lv,rv", [
    (5.0, []), ([], 5.0), ([], []), ([[], []], 5), (5, [[], []]),
    ([[], []], [[], []]), (np.array([]), 5), ([], np.array([])),
], ids=repr)
@pytest.mark.parametrize("relation", ["<=", ">=", "<", ">"])
def test_an_ordering_over_no_elements_is_unanswerable(lv, rv, relation):
    assert relation_within(lv, rv, relation) is None
    assert relation_holds_elementwise(lv, rv, relation, 1e-9) is None


@pytest.mark.parametrize("zero", [0, 0.0, -0.0, 0j])
def test_zero_is_the_zero_of_every_shape(zero):
    for vector in ([0.0, 0.0], [[0.0], [0.0]], np.zeros(3)):
        assert relation_within(vector, zero, "==") is True
        assert relation_within(zero, vector, "~=") is True
        assert relation_holds_elementwise(vector, zero, "==", 1e-9) is True
        assert relation_holds_elementwise(vector, zero, "!=", 1e-9) is False
    assert relation_within([0.0, 1.0], zero, "==") is False
    assert relation_holds_elementwise([0.0, 1.0], zero, "!=", 1e-9) is True


def test_two_empty_containers_are_one_value():
    assert relation_within([], [], "==") is True
    assert relation_within([], (), "~=") is True
    assert relation_holds_elementwise([], [], "==", 1e-9) is True
    assert relation_holds_elementwise([[], []], [[], []], "==", 1e-9) is True
    assert relation_within([], [], "!=") is False


def test_values_agree_reads_mismatched_shapes_as_no_answer():
    assert values_agree([], 5.0) is None
    assert values_agree(5.0, []) is None
    assert values_agree([5.0], [5.0, 5.0]) is None
    assert values_agree([], []) is True


@pytest.mark.parametrize("lv,rv", [(5.0, []), ([], 5.0), ([5.0, 5.0], 5.0),
                                   (5.0, [5.0, 5.0]), ([], [])], ids=repr)
def test_nothing_is_measured_over_a_mismatch(lv, rv):
    assert float_miss(lv, rv, "==") is None


def test_the_row_and_its_empty_input_line_agree():
    # the claim's row and the is_empty_safe line read one call of f at []
    reports = claims.check_conjectures(_five, [claim("f([]) == []", name="c")])
    assert reports[0].verdict == "falsified"
    assert "5.0" in reports[0].counterexample
