# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The documented input spellings beyond plain ascii: a radical without
parentheses, a superscript negative power, and the LaTeX commands
`\\equiv`, `\\leqslant`, `\\geqslant`, `\\varepsilon`, `\\varphi` and
`\\left`/`\\right`. Each lexicon example round-trips, reaches the same
verdict on its paired function before and after, and is the same claim
as its ascii spelling."""
import pytest

from mathema.conjecture import claim
from mathema.lexicon import EXAMPLE_FUNCTIONS, LEXICON
from mathema.spec import canonical_claim_text
from tests.test_claim_text_soundness import _verdict, assert_round_trips


@pytest.mark.parametrize("key, ascii_form", [
    ("sqrt_bare_radical", "for x in [1, 4], f(x) >= sqrt(x)"),
    ("power_superscript_negative", "for x in [1, 2], f(x) >= x^-1"),
    ("latex_equiv", "let g = mathema.lexicon.double, f =:= g"),
    ("latex_leqslant", "for x in [0, 1], f(x) <= 2"),
    ("latex_geqslant", "for x in [0, 1], f(x) >= 0"),
    ("latex_varepsilon", "for x in [0, 1], abs(f(x) - x) <= ε"),
    ("latex_varphi", "for φ in [0, 1], f(φ) <= 1"),
    ("latex_left_right_bars", "for x in [-1, 1], abs(f(x)) <= 2"),
])
def test_a_documented_spelling_is_its_ascii_claim(key, ascii_form):
    (fn,) = [fn for fn, keys in EXAMPLE_FUNCTIONS.values() if key in keys]
    law = LEXICON[key]
    canon = assert_round_trips(law, fn)
    assert canon == canonical_claim_text(claim(ascii_form))
    assert _verdict(fn, claim(law)) == "proven"
