# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The spellings that attach a machine number representation to a
binding are refused today, each with the message it gives.

This module covers exactly the pins an extension that gives these
spellings a meaning is allowed to replace: the five spellings
`let R be f32`, `let Z be i64`, `let x be f32`,
`for x in [0, 1] as f32` and `x in [0, 1e8] subset f32`, and the
reserved vocabulary around them (the named sets `R`, `Z`, `N`, `C` and
the representation names). Nothing else in the claim grammar is pinned
here; every other reading is pinned by the corpus and the grammar tests,
and has to stay as it is.
"""
import pytest

from mathema.conjecture import InvalidConjecture, claim
from mathema.domain import parse_binding, _parse_binding
from mathema.grammar import _BASE_SET_NAMES, _RESERVED_REPRESENTATIONS

_LET = ("`let {name} be {bound}` is reserved for representation declarations "
        "(binding a named set to a machine number representation such as "
        "i64 or f32), which are not supported yet; a free variable cannot "
        "be named {name!r} and a number representation name cannot be a "
        "bound")


@pytest.mark.parametrize("text,name,bound", [
    ("let R be f32, for x in [0, 1], f(x) >= 0", "R", "f32"),
    ("let Z be i64, for n in [0, 100] subset Z, f(n) >= 0", "Z", "i64"),
    ("let N be u64, for n in [0, 10] subset N, f(n) >= 0", "N", "u64"),
    ("let C be f64, f(z) >= 0", "C", "f64"),
    ("let x be f32, f(x) >= 0", "x", "f32"),
    ("let c be i64, f(c) >= 0", "c", "i64"),
])
def test_a_let_that_names_a_representation_is_refused_with_its_message(
        text, name, bound):
    with pytest.raises(InvalidConjecture) as raised:
        claim(text)
    assert str(raised.value) == _LET.format(name=name, bound=bound)


@pytest.mark.parametrize("bound", ["1", "[0,1]"])
def test_a_named_set_is_refused_as_a_let_subject_whatever_its_bound(bound):
    with pytest.raises(InvalidConjecture) as raised:
        claim(f"let R be {bound}, f(x) >= 0")
    assert str(raised.value) == _LET.format(name="R", bound=bound)


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


def test_the_reserved_vocabulary_is_as_it_is_today():
    assert _BASE_SET_NAMES == {"R", "Z", "N", "C"}
    assert _RESERVED_REPRESENTATIONS == {
        "bigint", "f16", "f32", "f64", "f64int", "i128", "i16", "i32",
        "i64", "i8", "u128", "u16", "u32", "u64", "u8"}
