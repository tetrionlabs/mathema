# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The extension surface's sampling seam: `sample_bound` draws a value
the way the probe route does for a declared bound, and `shrink` reduces
a failing witness. A registered family or a language package uses these
rather than re-implementing the probe's draws."""
import random

from mathema.domain import parse_binding
from mathema.interfaces.extension import sample_bound, shrink
from mathema.languages import StringLanguage, register_language, unregister_language


def test_sample_bound_draws_a_member_of_a_language_bound():
    register_language("letters", StringLanguage("letters", char_ok=str.isalpha,
                                                pool="abcXYZ"))
    try:
        bound = parse_binding("s in L[letters]")[1]
        rng = random.Random(1)
        for _ in range(50):
            value = sample_bound(bound, rng, "string")
            assert isinstance(value, str) and value.isalpha() or value == ""
    finally:
        unregister_language("letters")


def test_sample_bound_draws_inside_a_numeric_bound():
    rng = random.Random(2)
    for _ in range(50):
        assert 0.0 <= sample_bound((0.0, 1.0), rng) <= 1.0
    assert sample_bound(frozenset({"a", "b"}), rng) in ("a", "b")
    assert isinstance(sample_bound(parse_binding("n in [1, 5] subset Z")[1],
                                   rng, "int"), int)


def test_shrink_reduces_a_failing_string():
    assert shrink("aaab", lambda s: "b" in s) == "b"
