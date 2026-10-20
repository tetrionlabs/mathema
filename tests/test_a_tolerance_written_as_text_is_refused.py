# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A tolerance passed to `claim()` as text that is not a number (`"{abs:
0}"`) is refused when the claim is made, naming the two spellings it
takes, rather than failing later inside the proof."""
import pytest

from mathema.conjecture import InvalidConjecture, claim


def test_a_kind_written_as_a_string_is_refused_with_both_spellings():
    with pytest.raises(InvalidConjecture) as refused:
        claim("for x in [0, 1], x ~= x", tolerance="{abs: 0}")
    text = str(refused.value)
    assert "{abs: 0}" in text and "tolerance=1e-9" in text, text


def test_a_number_and_a_mapping_are_still_taken():
    assert claim("for x in [0, 1], x ~= x", tolerance=0).tolerance == 0
    assert claim("for x in [0, 1], x ~= x", tolerance={"abs": 0}).tolerance
