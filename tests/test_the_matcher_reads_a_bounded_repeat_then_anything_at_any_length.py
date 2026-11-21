# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The derivative matcher answers for a bounded repeat followed by
anything, the term of `[ab]{2,4000}` under "starts with", on texts of
any length: the union the derivative of a concatenation builds stays
flat, so the term does not deepen with each character read. A term the
matcher cannot finish within its budget fails with `MatchBudget`, never
with Python's own recursion limit."""
import pytest

from mathema import regular

ANYTHING = {"op": "repeat", "arg": {"op": "chars", "ranges": [[0, 0x10FFFF]]},
            "min": 0, "max": None}
STARTS = {"op": "concat", "args": [
    {"op": "repeat", "arg": {"op": "chars", "ranges": [[97, 98]]}, "min": 2, "max": 4000},
    ANYTHING]}


@pytest.mark.parametrize("length", [300, 999, 4000])
def test_a_bounded_repeat_then_anything_is_answered(length):
    holds = regular.matcher(STARTS)
    assert holds("a" * length)
    assert holds("ab" * (length // 2) + "zz")
    assert not holds("z" + "a" * length)
    assert regular.member(STARTS, "b" * length)


def test_the_answers_agree_with_the_pattern():
    import re
    pattern = re.compile(r"[ab]{2,4000}")
    holds = regular.matcher(STARTS)
    for text in ("", "a", "ab", "abz", "za", "a" * 5000 + "z", "zab"):
        assert holds(text) == (pattern.match(text) is not None), text


def _nested(depth):
    node = {"op": "literal", "codes": [97]}
    for _ in range(depth):
        node = {"op": "complement", "arg": {"op": "complement", "arg": node}}
    return node


def test_a_term_too_deep_to_read_fails_with_the_budget_not_recursion():
    deep = {"op": "concat", "args": [_nested(3000), ANYTHING]}
    try:
        answered = regular.member(deep, "ab")
    except regular.MatchBudget:
        return
    assert answered is True
