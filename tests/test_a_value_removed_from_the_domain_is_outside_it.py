# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`excluded_outside_domain[x]` over a domain written with `\\`: a value
the claim removes from the domain lies outside it, so the probe tries
it. A function that raises on it holds, as it does over the same set
spelled another way (`L[unicode, len >= 1]` for `L[unicode] \\ {""}`),
and one that returns cleanly on it falsifies with that value as the
witness. The same holds for a numeric domain (`R \\ {0}`)."""
import importlib.util

import pytest

from mathema.conjecture import check_conjectures, claim

needs_language = pytest.mark.skipif(
    importlib.util.find_spec("mathema_language") is None,
    reason="needs the mathema-language package")


def first_char(s: str) -> str:
    if s == "":
        raise ValueError("empty")
    return s[0]


def first_char_or_blank(s: str) -> str:
    return s[:1]


def reciprocal(x: float) -> float:
    if x == 0:
        raise ValueError("zero")
    return 1 / x


def reciprocal_or_zero(x: float) -> float:
    return 1 / x if x != 0 else 0.0


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law, route="best")])
    return p


@needs_language
def test_a_function_raising_on_the_removed_string_holds():
    p = _one(first_char, 'for s in L[unicode] \\ {""}, excluded_outside_domain(s)')
    assert p.verdict == "holds", (p.verdict, p.note)


@needs_language
def test_both_spellings_of_the_nonempty_strings_agree():
    removed = _one(first_char, 'for s in L[unicode] \\ {""}, excluded_outside_domain(s)')
    refined = _one(first_char, "for s in L[unicode, len >= 1], excluded_outside_domain(s)")
    assert removed.verdict == refined.verdict == "holds", (
        removed.verdict, removed.note, refined.verdict, refined.note)


@needs_language
def test_a_function_accepting_the_removed_string_falsifies_with_it():
    p = _one(first_char_or_blank,
             'for s in L[unicode] \\ {""}, excluded_outside_domain(s)')
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "s = '' (removed from the domain, L[unicode] \\ {\"\"})" in (
        p.counterexample), p.counterexample
    assert "accepted" in p.counterexample, p.counterexample


def test_a_function_raising_on_the_removed_number_holds():
    p = _one(reciprocal, "for x in R \\ {0}, excluded_outside_domain(x)")
    assert p.verdict == "holds", (p.verdict, p.note)


def test_a_function_accepting_the_removed_number_falsifies_with_it():
    p = _one(reciprocal_or_zero, "for x in R \\ {0}, excluded_outside_domain(x)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "x = 0" in p.counterexample, p.counterexample
