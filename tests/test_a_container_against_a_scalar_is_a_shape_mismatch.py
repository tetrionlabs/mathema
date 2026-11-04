# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim compares what the function returned with what the claim
wrote. A number and a container are different shapes, so they are unequal,
whichever side each is on, 0 included: the zero vector is written
`[0, 0]`. An empty container has no elements: it equals only another empty container, and an
ordering over it does not hold, since there is no element at which it
could (empty is not 0 and is not >= 0). A claim whose ordering fails only
where the result is empty is told so, with the narrowed domain as the way
out."""
import numpy as np
import pytest

from mathema import claims
from mathema._missing_words import remedy_statements
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
    (_zeros, "0"), (_zeros, "0.0"),
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
], ids=lambda v: getattr(v, "__name__", str(v)))
@pytest.mark.parametrize("relation", _RELATIONS)
def test_the_same_shape_is_compared(fn, written, expected, relation):
    assert _verdict(fn, f"f([]) {relation} {written}") == expected


@pytest.mark.parametrize("fn,written", [
    (_five, "[]"), (_text, "[]"), (_empty, "0"), (_empty, "5"),
    (_fives, "5"), (_five, "[5.0, 5.0]"), (_nested_empties, "0"),
    (_zeros, "0"),
], ids=lambda v: getattr(v, "__name__", str(v)))
def test_a_shape_mismatch_satisfies_not_equal(fn, written):
    assert _verdict(fn, f"f([]) != {written}") == "proven"


@pytest.mark.parametrize("fn,written", [
    (_empty, "[]"), (_zeros, "[0, 0]"), (_five, "5"),
], ids=lambda v: getattr(v, "__name__", str(v)))
def test_equal_values_fail_not_equal(fn, written):
    assert _verdict(fn, f"f([]) != {written}") == "falsified"


@pytest.mark.parametrize("fn,written", [
    (_five, "[]"), (_empty, "5"), (_empty, "[]"), (_empty_array, "5"),
    (_nested_empties, "5"), (_text, "[]"), (_five, "[[], []]"),
], ids=lambda v: getattr(v, "__name__", str(v)))
@pytest.mark.parametrize("relation", ["<=", ">=", "<", ">"])
def test_an_ordering_over_no_elements_does_not_hold(fn, written, relation):
    assert _verdict(fn, f"f([]) {relation} {written}") == "falsified"


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
    assert not values_agree(lv, rv)


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
def test_an_ordering_over_no_elements_is_false(lv, rv, relation):
    assert relation_within(lv, rv, relation) is False
    assert relation_holds_elementwise(lv, rv, relation, 1e-9) is False


def _ones(n):
    return [1.0] * n


class _Returning:
    """A callable that gives one value whatever it is called with."""

    def __init__(self, value):
        self.value = value
        self.__name__ = "returning"

    def __call__(self, x):
        return self.value


def _probe(fn, law):
    (probe,) = claims.check_conjectures(fn, [claim(law, name="c")])
    return probe


@pytest.mark.parametrize("law,narrowed", [
    ("for n in {0, 1, 2}, f(n) >= 0", "assuming n >= 1, "),
    ("for n in {0, 1, 2}, f(n) <= 1", "assuming n >= 1, "),
    ("for n in {0, 1, 2}, f(n) < n + 1", "assuming n >= 1, "),
    ("for n in [0, 2] subset Z, f(n) >= 0", "assuming n >= 1, "),
])
@pytest.mark.parametrize("route", ["best", "probe"])
def test_an_ordering_that_fails_only_at_an_empty_result_says_so(law, narrowed, route):
    (probe,) = claims.check_conjectures(_ones, [claim(law, name="c", route=route)])
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert "n = 0" in str(probe.counterexample), probe.counterexample
    assert "[] vs " in str(probe.counterexample), probe.counterexample
    assert remedy_statements(probe.note) == [narrowed + law], probe.note


def test_an_ordering_that_fails_elsewhere_too_offers_no_narrowing():
    probe = _probe(_ones, "for n in {0, 1, 2}, f(n) >= 2")
    assert probe.verdict == "falsified"
    assert remedy_statements(probe.note or "") == [], probe.note


def _empty_up_to_one(n):
    return [] if n <= 1 else [n]


def _always_empty(n):
    return []


def _empty_at_many(n):
    return [] if n <= 5 else [n]


def test_the_narrowed_domain_starts_past_every_empty_point():
    probe = _probe(_empty_up_to_one, "for n in {0, 1, 2, 3}, f(n) >= 0")
    assert remedy_statements(probe.note) == [
        "assuming n >= 2, for n in {0, 1, 2, 3}, f(n) >= 0"], probe.note
    assert "n = 0 and n = 1" in probe.sketch, probe.sketch
    assert "every other point" in probe.sketch, probe.sketch


def test_every_empty_point_is_named_or_counted():
    probe = _probe(_empty_at_many, "for n in {0, 1, 2, 3, 4, 5, 6}, f(n) >= 0")
    assert "and 3 more" in probe.sketch, probe.sketch
    assert "every other point" in probe.sketch, probe.sketch


def test_no_other_point_is_claimed_when_every_point_is_empty():
    probe = _probe(_always_empty, "for n in {0, 1, 2}, f(n) >= 0")
    assert probe.verdict == "falsified"
    assert "every other point" not in probe.sketch, probe.sketch
    assert remedy_statements(probe.note or "") == [], probe.note


def test_another_failure_is_named_beside_the_empty_point():
    probe = _probe(_ones, "for n in {0, 1, 2}, f(n) >= 2")
    assert "every other point" not in probe.sketch, probe.sketch


@pytest.mark.parametrize("empty", [
    {}, set(), "", range(0), (), [], frozenset()], ids=repr)
@pytest.mark.parametrize("law", ["for x in {1, 2}, f(x) >= 0",
                                 "for x in [0, 1], f(x) >= 0"])
def test_an_ordering_over_any_empty_value_is_falsified(empty, law):
    (probe,) = claims.check_conjectures(_Returning(empty), [claim(law, name="c")])
    assert probe.verdict == "falsified", (probe.verdict, probe.note)
    assert "an ordering" in probe.note, probe.note


@pytest.mark.parametrize("empty", [{}, set(), "", range(0)], ids=repr)
@pytest.mark.parametrize("relation", ["<=", ">=", "<", ">"])
def test_every_comparison_finds_an_ordering_over_an_empty_value_false(empty, relation):
    assert relation_within(empty, 0, relation) is False
    assert relation_holds_elementwise(empty, 0, relation, 1e-9) is False


def _one_by_one(A: np.ndarray):
    return np.asarray(A, dtype=float)


def test_a_1_by_1_result_is_a_shape_mismatch_and_says_so():
    probe = _probe(_one_by_one, "for A in [1,1]^(1,1), f(A) == 1")
    assert probe.verdict == "falsified"
    assert "equal in float" not in probe.counterexample, probe.counterexample
    assert "[[1.0]] vs 1" in probe.counterexample.replace("array(", ""), \
        probe.counterexample


def test_values_agree_has_no_broadcast():
    import inspect
    assert "broadcast" not in inspect.signature(values_agree).parameters


def test_an_empty_result_still_equals_an_empty_one_and_differs_from_a_number():
    assert _probe(_ones, "for n in {0, 1, 2}, f(n) == [1.0] * n").verdict == "proven"
    assert _probe(_ones, "f(0) == []").verdict == "proven"
    assert _probe(_ones, "f(0) != 5").verdict == "proven"
    assert _probe(_ones, "for n in {1, 2}, f(n) >= 0").verdict == "proven"


@pytest.mark.parametrize("zero", [0, 0.0, -0.0, 0j])
def test_zero_is_a_mismatch_like_any_number(zero):
    for vector in ([0.0, 0.0], [[0.0], [0.0]], np.zeros(3), []):
        assert relation_within(vector, zero, "==") is False
        assert relation_within(vector, zero, "!=") is True
        assert relation_holds_elementwise(vector, zero, "==", 1e-9) is False
        assert values_agree(vector, zero) is None
    assert relation_within([0.0, 0.0], [0, 0], "==") is True


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


def _quadratic(x: np.ndarray) -> float:
    return float(x @ x)


def test_a_premise_reads_0_as_the_zero_vector_and_a_claim_does_not():
    premised = "assuming x != 0, for x in [0, 1]^2, f(x) > 0"
    assert _verdict(_quadratic, premised) in ("holds", "proven")
    unpremised = "for x in [0, 1]^2, f(x) > 0"
    assert _verdict(_quadratic, unpremised) == "falsified"
    assert _verdict(_zeros, "f([]) != 0") == "proven"
