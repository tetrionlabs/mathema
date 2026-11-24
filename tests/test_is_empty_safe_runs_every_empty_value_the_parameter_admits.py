# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`is_empty_safe(xs)` is a statement about the empty input. A
parameter that admits more than one kind of sequence (`Sequence`
admits a list and a tuple) has more than one empty value, and each is
run: for a union, the empty value of every member type (`[]`, `()`,
`""`, `b""`, `{}`, `set()`), an optional's inner type included. A raise
on an input that is not empty says nothing about the empty one, so it
never falsifies emptiness safety."""
import math
from typing import Optional, Sequence, Union

import pytest

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


def size_ratio_text(xs: Union[list, str]) -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_dict(xs: Union[list, dict]) -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_set(xs: Union[list, set]) -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_bytes(xs: Union[list, bytes]) -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_bar(xs: "list | frozenset") -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_optional(xs: Optional[Union[list, str]]) -> float:
    if xs == []:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_or_zero_text(xs: Union[list, str]) -> float:
    if not xs:
        return 0.0
    return len(xs) / len(xs)


def size_ratio_or_zero_many(xs: Union[list, dict, set, bytes, str]) -> float:
    if len(xs) == 0:
        return 0.0
    return len(xs) / len(xs)


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


@pytest.mark.parametrize("fn, shown", [
    (size_ratio_text, "xs = ''"), (size_ratio_dict, "xs = {}"),
    (size_ratio_set, "xs = set()"), (size_ratio_bytes, "xs = b''"),
    (size_ratio_bar, "xs = frozenset()"), (size_ratio_optional, "xs = ''"),
], ids=lambda v: getattr(v, "__name__", None))
def test_the_empty_value_of_every_union_member_is_run(fn, shown):
    p = _row(fn)
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert shown in (p.counterexample or ""), p.counterexample
    assert "ZeroDivisionError" in (p.counterexample or ""), p.counterexample


@pytest.mark.parametrize("fn", [size_ratio_or_zero_text,
                                size_ratio_or_zero_many],
                         ids=lambda fn: fn.__name__)
def test_a_union_whose_every_empty_value_is_handled_is_still_proven(fn):
    p = _row(fn)
    assert p.verdict == "proven", (p.verdict, p.route, p.note)
