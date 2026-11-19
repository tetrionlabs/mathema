# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Regular-language terms: the dialect-free definition a text language
states (literals, character ranges, concatenation, union, intersection,
complement, repetition, over a stated alphabet), its canonical form and
hash, and the one question core asks of z3 about such terms: is there a
string inside these and outside those. The terms here are written by
hand; no pattern dialect is involved."""
import re

import pytest

from mathema import regular

z3 = pytest.importorskip("z3")

ALL = [[0, 0x10FFFF]]


def chars(*ranges):
    return {"op": "chars", "ranges": [list(r) for r in ranges]}


def lit(text):
    return {"op": "literal", "codes": [ord(c) for c in text]}


def cat(*args):
    return {"op": "concat", "args": list(args)}


def alt(*args):
    return {"op": "union", "args": list(args)}


def rep(arg, lo=0, hi=None):
    return {"op": "repeat", "arg": arg, "min": lo, "max": hi}


def doc(node, **more):
    return {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True,
            "language": node, **more}


LOWER = chars((97, 122))
DIGIT = chars((48, 57))
SLUG = rep(alt(LOWER, DIGIT, lit("-")), 1)
#: `[a-z0-9-]+$` under fullmatch: the slug, then at most one final newline
SLUG_DOLLAR = cat(SLUG, rep(lit("\n"), 0, 1))
ANY = rep(chars((0, 0x10FFFF)))


def test_the_hash_reads_the_meaning_and_never_the_source():
    a = doc(SLUG, source={"dialect": "python-re", "pattern": "[a-z0-9-]+", "python": "3.13.1"})
    b = doc(SLUG, source={"dialect": "python-re", "pattern": "[0-9a-z-]+", "python": "3.12.0"})
    assert regular.term_hash(a) == regular.term_hash(b)
    assert regular.term_hash(a) != regular.term_hash(doc(SLUG_DOLLAR))
    assert re.fullmatch(r"[0-9a-f]{64}", regular.term_hash(a))


def test_the_canonical_form_flattens_and_deduplicates():
    nested = cat(lit("a"), cat(lit("b"), {"op": "epsilon"}), alt(LOWER, alt(LOWER, DIGIT)))
    flat = cat(lit("a"), lit("b"), alt(LOWER, DIGIT))
    assert regular.canonical(nested) == regular.canonical(flat)
    assert regular.term_hash(doc(nested)) == regular.term_hash(doc(flat))
    assert regular.canonical(cat(lit("a"), {"op": "empty"})) == {"op": "empty"}


def test_an_inexact_definition_hashes_both_bounds():
    inexact = {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": False,
               "at_least": ANY, "at_most": {"op": "empty"}}
    assert regular.term_hash(inexact) != regular.term_hash(doc(ANY))
    assert regular.bounds(inexact) == (regular.canonical({"op": "empty"}),
                                       regular.canonical(ANY))
    assert regular.bounds(doc(SLUG)) == (regular.canonical(SLUG), regular.canonical(SLUG))


@pytest.mark.parametrize("bad", [
    {"kind": "regular_language", "version": 2, "alphabet": ALL, "exact": True, "language": SLUG},
    {"kind": "grammar", "version": 1, "alphabet": ALL, "exact": True, "language": SLUG},
    doc({"op": "lookahead", "arg": SLUG}),
    doc(chars((122, 97))),
    doc(rep(LOWER, 3, 1)),
    doc({"op": "literal", "text": "a"}),
    {"kind": "regular_language", "version": 1, "alphabet": ALL, "exact": True},
])
def test_a_document_outside_the_schema_is_not_a_definition_questions_are_asked_of(bad):
    with pytest.raises(regular.InvalidTerm):
        regular.bounds(bad)
    assert not regular.is_definition(bad)


def test_no_string_is_in_the_slug_and_outside_the_slug_with_a_final_newline():
    found = regular.find_member(ALL, inside=[SLUG], outside=[SLUG_DOLLAR])
    assert (found.status, found.member) == ("none", None)


def test_z3_alone_finds_the_trailing_newline():
    found = regular.find_member(ALL, inside=[SLUG_DOLLAR], outside=[SLUG])
    assert found.status == "member"
    assert found.member.endswith("\n")
    assert re.fullmatch(r"[a-z0-9-]+\n", found.member)


@pytest.mark.parametrize("inside,outside,pattern", [
    ([rep(LOWER, 2, 3)], [rep(LOWER, 3, 3)], r"[a-z]{2}"),
    ([cat(lit("ab"), ANY), cat(ANY, lit("ba"))], [], r"ab(.|\n)*ba|aba"),
    ([{"op": "complement", "arg": rep(LOWER)}], [], r"(.|\n)*[^a-z](.|\n)*"),
    ([{"op": "inter", "args": [rep(alt(LOWER, DIGIT), 1), {"op": "complement", "arg": rep(LOWER)}]}],
     [], r"[a-z0-9]*[0-9][a-z0-9]*"),
    ([rep(chars((0x1F600, 0x1F64F)), 1, 1)], [], "[\U0001F600-\U0001F64F]"),
    ([rep(chars((0x30000, 0x10FFFF)), 2, 2)], [], "[\U00030000-\U0010FFFF]{2}"),
])
def test_a_member_found_is_a_member_as_python_reads_the_same_language(inside, outside, pattern):
    found = regular.find_member(ALL, inside=inside, outside=outside)
    assert found.status == "member"
    assert re.fullmatch(pattern, found.member), found.member


@pytest.mark.parametrize("inside,outside", [
    ([rep(LOWER, 1), rep(DIGIT, 1)], []),
    ([{"op": "empty"}], []),
    ([rep(LOWER)], [rep(alt(LOWER, DIGIT))]),
    ([lit("ab")], [cat(lit("a"), lit("b"))]),
    ([ANY], [alt(rep(LOWER), {"op": "complement", "arg": rep(LOWER)})]),
])
def test_an_empty_question_has_no_member(inside, outside):
    assert regular.find_member(ALL, inside=inside, outside=outside).status == "none"


def test_a_large_class_under_a_repeat_is_asked_over_its_atoms():
    word = chars((48, 57), (65, 90), (97, 122), (0xC0, 0x24F), (0x400, 0x4FF), (0x4E00, 0x9FFF))
    found = regular.find_member(ALL, inside=[rep(cat(chars((0, 9), (11, 0x10FFFF)), word), 0, 2)],
                                outside=[rep(word)], timeout_ms=20000)
    assert found.status == "member"


def test_a_narrower_alphabet_bounds_the_complement():
    ascii_only = [[0, 127]]
    found = regular.find_member(ascii_only, inside=[{"op": "complement", "arg": rep(LOWER)}],
                                outside=[])
    assert found.status == "member" and all(ord(c) < 128 for c in found.member)
    none = regular.find_member([[97, 122]], inside=[{"op": "complement", "arg": rep(LOWER)}],
                               outside=[])
    assert none.status == "none"
