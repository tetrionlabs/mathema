# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Shrinking a failing witness to a minimal one: remove as much as
possible, then simplify what remains (unicode -> ascii -> a/space)."""
from mathema._shrink import shrink


def test_shrink_removes_incidental_content_down_to_the_trigger():
    # the failure is triggered by a 'Z'; everything else is incidental
    got = shrink("aaaZbbbbéélong", lambda s: "Z" in s)
    assert got == "Z"


def test_shrink_reaches_the_minimal_length_and_simplest_chars():
    got = shrink("qWeRtYuIop", lambda s: len(s) >= 3)
    assert len(got) == 3
    assert got == "aaa"                      # simplified to the plainest char


def test_shrink_can_reach_the_empty_string_when_that_still_fails():
    got = shrink("whatever", lambda s: True)   # everything fails
    assert got == ""


def test_shrink_is_bounded_and_leaves_non_strings_untouched():
    # a pathological predicate cannot run unbounded
    calls = []

    def pred(s):
        calls.append(s)
        return True

    shrink("abcdefghij", pred, max_steps=5)
    assert len(calls) <= 5
    assert shrink(12345, lambda v: True) == 12345    # non-string unchanged
