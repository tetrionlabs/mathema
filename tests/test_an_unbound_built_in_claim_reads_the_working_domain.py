# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A built-in claim that binds no domain is judged over the working
domain the function's own guards leave, as a value claim is: a raise
guard on variance < 0 leaves [0, oo), where math.sqrt is inside its
number set, and a guard refusing every side outside {"buy", "sell"}
leaves that set, where the function is defined. The record states the
working domain, and the statement stays as written."""
import math
from typing import Literal

from mathema.conjecture import check_conjectures, claim


def volatility(variance: float) -> float:
    if variance < 0:
        raise ValueError("variance must be nonnegative")
    return math.sqrt(variance)


def order_sign(side: str) -> int:
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    return 1 if side == "buy" else -1


def order_sign_literal(side: Literal["buy", "sell"]) -> int:
    return 1 if side == "buy" else -1


def unguarded_root(variance: float) -> float:
    return math.sqrt(variance)


def _one(fn, text):
    (p,) = check_conjectures(fn, [claim(text)])
    return p


def test_number_set_safety_behind_a_raise_guard_is_proven():
    bound = _one(volatility,
                 "for variance in [-1, 1], is_number_set_safe(variance)")
    assert bound.verdict == "proven", (bound.verdict, bound.note)
    p = _one(volatility, "is_number_set_safe(variance)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "for variance" not in p.statement, p.statement
    assert "the working domain is variance in [0, oo)" in (p.note or ""), \
        p.note
    working = (p.meta or {}).get("mathema.working_domain", {})
    assert working.get("variance") == "[0, oo)", p.meta
    assert working.get("guards") == ["variance < 0"], p.meta


def test_without_a_guard_number_set_safety_still_falsifies():
    p = _one(unguarded_root, "is_number_set_safe(variance)")
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_definedness_behind_a_guard_to_a_set_is_proven():
    for fn, text in ((order_sign, 'for side in {"buy", "sell"}, is_defined(f)'),
                     (order_sign_literal, "is_defined(f)")):
        p = _one(fn, text)
        assert p.verdict == "proven", (fn.__name__, p.verdict, p.note)
    p = _one(order_sign, "is_defined(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch, p.note)
    assert "no evaluable inputs" not in (p.note or ""), p.note
    assert 'the working domain is side in {"buy", "sell"}' in (p.note or ""), \
        p.note
