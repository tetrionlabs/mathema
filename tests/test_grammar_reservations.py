# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The representation-declaration spelling is reserved, not squattable.

`let Z be i64` will one day rebind a named set's machine carrier, the
same shape `let |inf| be 1e6` already rebinds infinity. Until it does,
the parser refuses both halves of the spelling with guidance, so no
free-variable binding accidentally takes the meaning.
"""
import pytest

from mathema.conjecture import InvalidConjecture, claim


@pytest.mark.parametrize("text", [
    "let Z be i64, for n in [0,100] subset Z, f(n) >= 0",
    "let R be f32, for x in [0,1], f(x) >= 0",
    "let N be u64, for n in [0,10] subset N, f(n) >= 0",
    # a carrier name as a bound is reserved whatever the variable
    "let c be i64, f(c) >= 0",
    "let step be f32, f(step) >= 0",
])
def test_the_representation_spelling_is_reserved(text):
    with pytest.raises(InvalidConjecture, match="reserved for representation"):
        claim(text)


def test_ordinary_let_shapes_are_untouched():
    claim("let c be [-1e6,1e6], for x in [0,10], f(x) + c >= 0")
    claim("let c be 2.0, f(c) >= 0")
    claim("let |inf| be 1e12, for x in [0, oo], f(x) >= 0")
    claim("let g = math.sqrt, for x in (0,100], g(x) >= 0")
