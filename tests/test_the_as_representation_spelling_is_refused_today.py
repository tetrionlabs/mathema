# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `as <representation>` spelling on a binding is refused today, with
the message it gives.

This module covers the current refusal of the `as` form
(`for x in [0, 1] as f32`, `x in [0, 1] : float as f32` and
`x in [0, 1e8] subset f32`) and nothing else. It is the only pin the
extension that gives `as <representation>` a meaning replaces; the `let`
refusals are pinned permanently in
`test_the_let_representation_spellings_stay_refused`.
"""
import pytest

from mathema.conjecture import InvalidConjecture, claim
from mathema.domain import parse_binding, _parse_binding

@pytest.mark.parametrize("text,binding,bound", [
    ("for x in [0, 1] as f32, f(x) >= 0", "x in [0, 1] as f32", "[0, 1] as f32"),
    ("for x in [0, 1e8] subset f32, f(x) >= 0",
     "x in [0, 1e8] subset f32", "[0, 1e8] subset f32"),
    ("for x in [0, 1] : float as f32, f(x) >= 0",
     "x in [0, 1] : float as f32", "[0, 1] as f32"),
])
def test_a_binding_with_a_representation_is_refused_with_its_message(
        text, binding, bound):
    said = (f"{binding!r}: {bound!r} isn't a recognized interval, discrete "
            f"set, or named set (R/Z/N) for 'x'")
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == said


@pytest.mark.parametrize("binding", ["x in [0, 1] as f32",
                                     "x in [0, 1e8] subset f32"])
def test_parse_binding_reads_no_binding_from_a_representation_spelling(binding):
    assert parse_binding(binding) is None
    assert isinstance(_parse_binding(binding), str)
