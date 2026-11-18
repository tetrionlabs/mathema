# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `let` spellings that name a machine number representation stay
refused, each with the message it gives.

This is permanent behaviour: `let R be f32`, `let Z be i64`,
`let x be f32` and the other `let NAME be <representation>` and
`let <named set> be ...` forms are reserved, and a claim that declares
one name with both `let ... be ...` and `for ... in ...` is refused. These
pins are not replaced by a representation spelling on a binding.
"""
import pytest

from mathema.conjecture import ConflictingDomainBinding, InvalidConjecture, claim
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


def test_a_name_declared_by_let_and_by_for_is_refused_with_its_message():
    with pytest.raises(ConflictingDomainBinding) as raised:
        claim("let x be [0, 1], for x in [0, 2], f(x) >= 0")
    assert str(raised.value) == (
        "['x'] declared with both 'let ... be ...' and 'for ... in ...' "
        "in the same claim, pick one")


@pytest.mark.parametrize("text", [
    "let R be f32, for R in [0, 1], f(R) >= 0",
    "let x be f32, for x in [0, 1], f(x) >= 0",
])
def test_a_let_that_names_a_representation_is_refused_before_the_for_is_read(text):
    with pytest.raises(InvalidConjecture, match="reserved for representation"):
        claim(text)


def test_the_reserved_vocabulary_is_as_it_is_today():
    assert _BASE_SET_NAMES == {"R", "Z", "N", "C"}
    assert _RESERVED_REPRESENTATIONS == {
        "bigint", "f16", "f32", "f64", "f64int", "i128", "i16", "i32",
        "i64", "i8", "u128", "u16", "u32", "u64", "u8"}
