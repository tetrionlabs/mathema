# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A code point range written as a tuple is read as the list it
stands for, before the definition is checked, made canonical or hashed:
`[(97, 122)]` and `[[97, 122]]` are one definition, with one canonical
text and one hash, in the alphabet and inside a `chars` node alike."""
from mathema import regular

FULL = [[0, 0x10FFFF]]


def _document(alphabet, ranges):
    return {"kind": "regular_language", "version": 1, "alphabet": alphabet, "exact": True,
            "language": {"op": "repeat", "arg": {"op": "chars", "ranges": ranges},
                         "min": 1, "max": None}}


LISTS = _document([[0, 127]], [[97, 122], [48, 57]])
TUPLES = _document([(0, 127)], [(97, 122), (48, 57)])


def test_tuple_ranges_validate():
    assert regular.validate(TUPLES) is None


def test_tuple_ranges_have_the_same_canonical_text_and_hash():
    assert regular.canonical_text(TUPLES) == regular.canonical_text(LISTS)
    assert regular.term_hash(TUPLES) == regular.term_hash(LISTS)


def test_tuple_ranges_hold_the_same_texts():
    for text in ("a", "a1", "z9", "", "A", "é"):
        assert regular.contains(TUPLES, text) == regular.contains(LISTS, text), text


def test_a_range_of_other_than_two_code_points_is_still_refused():
    import pytest
    for ranges in ([(97,)], [(97, 98, 99)], [[97]]):
        with pytest.raises(regular.InvalidTerm):
            regular.validate(_document(FULL, ranges))
