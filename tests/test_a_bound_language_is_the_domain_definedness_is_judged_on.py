# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_language_defined reads a bound language as the declared domain:
every member must reach an answer (a return, or an exit status, the
program's answer to its input), so any traceback on a member falsifies,
whatever its type and whether or not the function guards it; a
non-member must be refused (any raise, an exit included, when the
language declares no refusal), and a value returned for one falsifies.
With no language bound, the function's refusals define its language:
exits, guarded raises and deliberate raises are refusals, the record
states the boundary it inferred, and only an accidental unguarded crash
falsifies."""
import argparse
import sys

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.languages import (StringLanguage, register_language,
                               unregister_language)

DIGITS = StringLanguage("digits", char_ok=str.isdigit, pool="0123456789",
                        outside_pool="ab")
#: the strings over the ASCII digits 0 to 9, the empty string included
ASCII_DIGITS = StringLanguage("ascii_digits", char_ok=lambda c: c in "0123456789",
                              pool="0123456789", outside_pool="ab")


def setup_module(module):
    register_language("digits", DIGITS)
    register_language("ascii_digits", ASCII_DIGITS)


def teardown_module(module):
    unregister_language("digits")
    unregister_language("ascii_digits")


def to_int(s: str) -> int:
    # int("") raises ValueError, and "" is a member of L[digits]
    return int(s)


def checked_int(s: str) -> int:
    if not s:
        raise ValueError("an empty count")
    return int(s)


def exits_with_the_count(s: str) -> None:
    sys.exit(len(s))


def counts(s: str) -> int:
    return len(s)


def digit_sum(s: str) -> int:
    if not all(c in "0123456789" for c in s):
        raise ValueError("not a string of ASCII digits")
    return sum(int(c) for c in s)


def parsed(s: str) -> int:
    parser = argparse.ArgumentParser(prog="parsed")
    parser.add_argument("--n", type=int, required=True)
    return parser.parse_args(["--n", s]).n


def _v(fn, text):
    (p,) = check_conjectures(fn, [claim(text)])
    return p


@pytest.mark.parametrize("fn", [to_int, checked_int])
def test_a_deliberate_raise_on_a_member_falsifies(fn):
    p = _v(fn, "for s in L[digits], is_language_defined(s)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "s = '' (inside L[digits]) raised ValueError" in p.counterexample, \
        p.counterexample


def test_an_exit_on_a_member_is_its_answer():
    p = _v(exits_with_the_count, "for s in L[digits], is_language_defined(s)")
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_a_value_returned_for_a_non_member_falsifies():
    p = _v(counts, "for s in L[digits], is_language_defined(s)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "(outside L[digits])" in p.counterexample, p.counterexample
    assert "returned" in p.counterexample, p.counterexample


def test_a_function_answering_members_and_refusing_the_rest_holds():
    # true: every member of L[ascii_digits] (the empty string included)
    # passes the all-digits test, and int of one ASCII digit never
    # raises, so each member gets a return; every non-member holds a
    # character outside 0..9, so the test fails and ValueError refuses it
    p = _v(digit_sum, "for s in L[ascii_digits], is_language_defined(s)")
    assert p.verdict == "holds", (p.verdict, p.counterexample)


def test_with_no_language_bound_an_exit_is_a_refusal_the_note_states():
    p = _v(parsed, "is_language_defined(s)")
    assert p.verdict == "holds", (p.verdict, p.counterexample)
    assert "refused: '' (SystemExit (exit code 2))" in p.note, p.note
