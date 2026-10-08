# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A parameter whose values are a finite set of strings (a `Literal`, a
str `Enum`, a guard `if side not in {...}: raise`) is read over that set:
a claim over it alone is proven by visiting every member; in a mixed
function each member is one case of the derive route, and the claim is
proven only when every case is. An Enum parameter is called with its
members, and `is_representation_safe` on it asks whether the member and
its value agree. `is_language_defined` over a finite set asks that every
member works."""
from enum import Enum
from typing import Literal

import pytest

import mathema
from mathema.conjecture import check_conjectures, claim


class Side(Enum):
    BUY = "buy"
    SELL = "sell"


def fee(side: Literal["buy", "sell"], qty: float) -> float:
    return qty * 0.01 if side == "buy" else qty * 0.02


def fee_enum(side: Side, qty: float) -> float:
    return qty * 0.01 if side is Side.BUY else qty * 0.02


def rank(c: Literal["red", "green"]) -> int:
    return {"red": 1, "green": 2}[c]


def guarded_rank(c: str) -> int:
    if c not in {"red", "green"}:
        raise ValueError("unknown colour")
    return {"red": 1, "green": 2}[c]


def tag(side: Side) -> str:
    return side.value if isinstance(side, Side) else "?"


def fee_either(side: Side, qty: float) -> float:
    return qty * 0.01 if Side(side) is Side.BUY else qty * 0.02


def _one(fn, law):
    (p,) = check_conjectures(fn, [claim(law)])
    return p


def test_a_literal_parameter_is_proven_by_visiting_every_member():
    p = _one(rank, "f(c) >= 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), (p.verdict, p.note)
    assert "2 points" in (p.sketch or ""), p.sketch


def test_a_guard_to_a_set_is_the_working_domain():
    p = _one(guarded_rank, "f(c) >= 1")
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), (p.verdict, p.note)
    assert 'the working domain is c in {"green", "red"}' in (p.note or ""), p.note
    rec = mathema.check(guarded_rank)
    assert "is_representation_safe[c]" not in {q.name for q in rec.probes}


def test_a_mixed_function_is_split_per_member_on_derive():
    # true for sell (qty/50 >= qty/50), false for buy (qty/100 >= qty/50)
    p = _one(fee, "for qty in [0, 100], f(side, qty) >= qty * 0.02")
    assert p.verdict == "falsified", (p.verdict, p.sketch, p.note)
    assert "side = 'buy'" in (p.counterexample or ""), p.counterexample
    p = _one(fee, "for qty in [0, 100], f(side, qty) >= 0")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route.startswith("derive"), p.route
    assert '{"buy"}' in (p.sketch or "") and '{"sell"}' in (p.sketch or ""), p.sketch


def test_an_enum_parameter_is_called_with_its_members():
    p = _one(fee_enum, "for qty in [0, 100], f(side, qty) <= qty * 0.02")
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample, p.note)
    p = _one(fee_enum, "for qty in [0, 100], f(side, qty) >= qty * 0.02")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "buy" in (p.counterexample or ""), p.counterexample


def test_representation_on_an_enum_compares_the_member_with_its_value():
    p = _one(tag, "is_representation_safe(side)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "Side.BUY" in (p.counterexample or "") and "'buy'" in (p.counterexample or ""), \
        p.counterexample
    # fee_enum reads the value spelling as not-BUY and answers differently
    p = _one(fee_enum, "is_representation_safe(side)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert _one(fee_either, "is_representation_safe(side)").verdict in ("holds", "proven")
    names = {q.name for q in mathema.check(fee_enum).probes}
    assert "is_representation_safe[side]" in names
    assert "is_representation_safe[qty]" in names


@pytest.mark.parametrize("fn", [rank, guarded_rank])
def test_language_defined_over_a_finite_set_is_every_member_works(fn):
    p = _one(fn, "is_language_defined(c)")
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample, p.note)
    assert "member" in (p.note or "") or "member" in (p.sketch or ""), (p.note, p.sketch)
