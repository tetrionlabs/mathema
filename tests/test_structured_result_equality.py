# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Two structured results compare by their values, whatever the leaves
are: a parser returning nested lists that hold `None` or strings is
equal to itself, and unequal to a different structure. The numeric
fast path (numpy, elementwise with tolerance) is for numeric leaves
only; a `None` leaf is not a NaN, and a string leaf is not a number."""
from mathema.probing import relation_holds_elementwise


def test_equal_nested_lists_with_none_leaves_are_equal():
    value = [[-1, None, None], {"a": 1}]
    assert relation_holds_elementwise(value, value, "==", 1e-9) is True
    assert relation_holds_elementwise(value, value, "!=", 1e-9) is False


def test_equal_lists_with_string_leaves_are_equal():
    assert relation_holds_elementwise(["a", None], ["a", None], "==", 1e-9) is True
    assert relation_holds_elementwise([("k", "v")], [("k", "v")], "==", 1e-9) is True


def test_different_structures_with_none_leaves_are_unequal():
    assert relation_holds_elementwise([None, 1], [None, 2], "==", 1e-9) is False
    assert relation_holds_elementwise(["a"], ["b"], "!=", 1e-9) is True


def test_numeric_leaves_keep_their_tolerance():
    assert relation_holds_elementwise([1.0, 2.0], [1.0 + 1e-12, 2.0], "==", 1e-9) is True
    assert relation_holds_elementwise([[1, 2], [3, 4]], [[1, 2], [3, 5]], "<=", 0.0) is True


def test_an_ordering_over_non_numeric_leaves_is_unanswerable():
    assert relation_holds_elementwise(["a"], ["b"], "<=", 0.0) is None


def test_a_ragged_structure_is_compared_leaf_by_leaf():
    value = [True, False, [1.5, False]]
    assert relation_holds_elementwise(value, value, "==", 1e-9) is True
    assert relation_holds_elementwise([1, [2, 3]], [1, [2, 4]], "==", 1e-9) is False
    assert relation_holds_elementwise([1, [2, 3]], [1, [2, 4]], "<=", 0.0) is True
