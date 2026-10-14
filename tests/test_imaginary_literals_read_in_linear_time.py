# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An imaginary literal (`2i`, `1.5i`, `3ⅈ`) is rewritten to Python's
j-suffix in one pass whose cost grows with the length of the text, so a
claim or probe input holding a long run of digits reads promptly."""
import pytest

from mathema import _timeout
from mathema.grammar import _imaginary_suffix_to_j


@pytest.mark.parametrize("text", [
    "9" * 20000,
    "1." + "9" * 20000 + " x",
    "9" * 20000 + " ⅈ x",
], ids=["digits", "decimal", "unicode-suffix"])
def test_a_long_digit_run_reads_within_the_fast_cap(text):
    out = _timeout._with_timeout(lambda: _imaginary_suffix_to_j(text),
                                 _timeout.FAST_TIMEOUT_SECONDS)
    assert out.startswith(text[:10].replace("ⅈ", "1j"))


@pytest.mark.parametrize("text, expected", [
    ("2i", "2j"), ("1.5i", "1.5j"), (".5i", ".5j"), ("1.i", "1.j"),
    ("3ⅈ", "3j"), ("3 𝑖", "3j"), ("ⅈ", "1j"), ("x2i", "x2i"),
    ("a.5i", "a.5i"), ("2in", "2in"), ("f(x) == 2i*x", "f(x) == 2j*x"),
    ("12.25 ⅈ + 4i", "12.25j + 4j"),
])
def test_imaginary_literals_rewrite_to_the_j_suffix(text, expected):
    assert _imaginary_suffix_to_j(text) == expected
