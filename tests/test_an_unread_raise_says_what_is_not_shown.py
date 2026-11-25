# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""What an unread raise's reason says is what the reading did not show:
an argument, statement or test before the raise is not shown to be
unable to raise, which is not a claim that it can. A region where a
function raises names the class only when the raise was read as raising
that class; otherwise it says the function raises, and the executed
witness names what was raised."""
import math

from mathema.conjecture import check_conjectures, claim


def roots_in_its_message(x: float) -> float:
    if x > 0:
        raise ValueError(math.sqrt(x))
    return x


def keyword_message(x: float) -> float:
    if x == 0.3:
        raise ValueError(msg="z")
    return 2 * x


def plain_message(x: float) -> float:
    if x == 0.3:
        raise ValueError("z")
    return 2 * x


def test_an_unread_argument_is_described_as_not_shown_unable_to_raise():
    (row,) = check_conjectures(roots_in_its_message, [
        claim("for x in [1, 5], raises(f(x), ValueError)", route="derive")])
    text = (row.sketch or "") + (row.note or "")
    assert "is not shown to be unable to raise" in text, text
    assert "may itself raise" not in text, text


def test_a_raise_region_does_not_name_a_class_the_raise_was_not_read_to_raise():
    with __import__("pytest").raises(TypeError):
        keyword_message(0.3)
    rows = check_conjectures(keyword_message, [
        claim("for x in [-1, 1], f =:= g", funcs={"g": plain_message})])
    text = " ".join((r.sketch or "") + " " + (r.counterexample or "") for r in rows)
    assert "f(x) raises ValueError" not in text, text
    assert rows[0].verdict != "proven", rows[0].verdict
