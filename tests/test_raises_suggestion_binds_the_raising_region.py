# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A raises(...) suggestion read from a guard is bound to the region
where that guard raises, with each end open or closed as the guard
states it, and is proven or holds there. A guard whose region mathema
cannot state gives no raises(...) suggestion, never a falsified one."""
import pytest

from mathema import check
from mathema.languages import resolves
from mathema.suggest import suggest_claims


def below_zero(x: float) -> float:
    if x < 0:
        raise ValueError("negative")
    return x


def at_or_below_zero(x: float) -> float:
    if x <= 0:
        raise ValueError("not positive")
    return x


def probability(p: float) -> float:
    if not 0 <= p <= 1:
        raise ValueError("not a probability")
    return p * (1 - p)


def zero_only(x: float) -> float:
    if x == 0:
        raise ValueError("zero")
    return 1.0 / x


def second_guarded(x: float, y: float) -> float:
    if y < 0:
        raise ValueError("y negative")
    return x + y


def side_sign(side: str) -> int:
    if side not in {"buy", "sell"}:
        raise ValueError("unknown side")
    return 1 if side == "buy" else -1


def ordered(x: float, y: float) -> float:
    if x > y:
        raise ValueError("x above y")
    return y - x


def either_not_positive(sig: float, t: float) -> float:
    if sig <= 0 or t <= 0:
        raise ValueError("sig and t must be positive")
    return sig * t


def first_of(scores: list) -> float:
    if not scores:
        raise ValueError("empty")
    return scores[0]


def _raises_row(fn, name):
    (row,) = [p for p in check(fn).probes if p.name == name]
    return row


@pytest.mark.parametrize("fn, name, binding", [
    (below_zero, "raises[x]", "for x in (-oo, 0), "),
    (at_or_below_zero, "raises[x]", "for x in (-oo, 0], "),
    (probability, "raises[p]", "for p in (-oo, 0) ∪ (1, oo), "),
    (zero_only, "raises[x]", "for x in {0}, "),
    (second_guarded, "raises[y]", "for y in (-oo, 0), "),
    (ordered, "raises[x]", "assuming x > y, "),
    (either_not_positive, "raises[sig]", "for sig in (-oo, 0], "),
    (either_not_positive, "raises[t]", "for t in (-oo, 0], "),
], ids=lambda v: getattr(v, "__name__", None))
def test_a_raises_suggestion_is_bound_to_where_the_guard_raises(
        fn, name, binding):
    (s,) = [c for c in suggest_claims(fn) if c.name == name]
    assert s.raw.startswith(binding), s.raw
    row = _raises_row(fn, name)
    assert row.verdict in ("proven", "holds"), (
        row.statement, row.verdict, row.counterexample)


@pytest.mark.skipif(not resolves("unicode"),
                    reason="needs the unicode string language")
def test_a_guard_on_a_set_of_strings_binds_the_strings_outside_it():
    (s,) = [c for c in suggest_claims(side_sign) if c.name == "raises[side]"]
    assert s.raw.startswith('for side in L[unicode] \\ {"buy", "sell"}, '), \
        s.raw
    row = _raises_row(side_sign, "raises[side]")
    assert row.verdict in ("proven", "holds"), (row.statement, row.verdict)


@pytest.mark.parametrize("fn", [below_zero, at_or_below_zero, probability,
                                zero_only, second_guarded, side_sign,
                                ordered, either_not_positive, first_of],
                         ids=lambda f: f.__name__)
def test_no_raises_suggestion_is_falsified(fn):
    for p in check(fn).probes:
        if p.name.startswith("raises["):
            assert p.verdict != "falsified", (
                p.statement, p.counterexample)
