# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_empty_safe(xs)` is a statement about the empty input. A
parameter that admits more than one kind of sequence (`Sequence`
admits a list and a tuple) has more than one empty value, and each is
run. A raise on an input that is not empty says nothing about the
empty one, so it never falsifies emptiness safety."""
import math
from typing import Sequence

from mathema.conjecture import check_conjectures, claim


def mean_or_zero_for_an_empty_list(xs: Sequence[float]) -> float:
    if xs == []:
        return 0.0
    return sum(xs) / len(xs)


def mean_or_zero(xs: Sequence[float]) -> float:
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def log_of_head(xs: list[float]) -> float:
    if not xs:
        return 0.0
    return math.log(xs[0])


def _row(fn):
    rows = check_conjectures(fn, [claim("is_empty_safe(xs)")])
    return next(r for r in rows if r.name.startswith("is_empty_safe")
                and not r.name.endswith("[float]"))


def test_an_empty_tuple_that_raises_is_not_proven_safe():
    p = _row(mean_or_zero_for_an_empty_list)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert "()" in (p.counterexample or ""), p.counterexample


def test_every_empty_sequence_handled_is_still_proven():
    p = _row(mean_or_zero)
    assert p.verdict == "proven", (p.verdict, p.route, p.note)


def test_a_raise_on_a_non_empty_input_does_not_falsify_emptiness_safety():
    p = _row(log_of_head)
    assert p.verdict != "falsified", (p.verdict, p.route, p.counterexample)
