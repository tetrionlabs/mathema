# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim over sequences is its mathematics over non-empty lists
plus its empty-input line.

`R^n` means n >= 1, and an unbound list starts at length one too, so a
claim's proof (and its float line) is over non-empty inputs. What f
does with the empty list is the line `is_empty_safe[x]` under the
claim: f is called the way the claim calls it, with `x = []`, and an
unguarded raise there falsifies the line, with that call as its
witness, and the claim with it. A function that returns on the empty
list, or refuses it behind an explicit guard, keeps its claim.
"""
from __future__ import annotations

import math

import pytest

from mathema.claims import check_conjectures, claim


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def ema_scaled(x: list, alpha: float, scale: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y * scale


def guarded_ema(x: list, alpha: float) -> float:
    if not x:
        raise ValueError("x is empty")
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


def mean_of_list(x: list) -> float:
    total = 0.0
    for v in x:
        total += v
    return total / len(x)


def two_pass_variance(xs: list) -> float:
    total = 0.0
    for x in xs:
        total += x
    mean = total / len(xs)
    sq = 0.0
    for x in xs:
        sq += (x - mean) ** 2
    return sq / len(xs)


def rms(signal: list) -> float:
    total = 0.0
    for v in signal:
        total += v * v
    return math.sqrt(total / len(signal))


def total(xs: list) -> float:
    y = 0.0
    for v in xs:
        y = y + v
    return y


#: (function, claim, its sequence) whose mathematics stands over
#: non-empty lists while f raises on the empty one with no guard
STUMBLES = [
    (ema, "f(x, 1.0) == x[-1]", "x"),
    (ema, "for alpha in [1, 1], f(x, alpha) == x[-1]", "x"),
    (ema, "for alpha in [0, 1], min(x) <= f(x, alpha)", "x"),
    (ema, "for alpha in [0, 1], f(x, alpha) <= max(x)", "x"),
    (ema, "for alpha in [0, 1], f(x, alpha) >= min(x)", "x"),
    (ema_scaled, "f(x, 1.0, 2.0) == 2 * x[-1]", "x"),
    (mean_of_list, "f(x) * 0.0 == 0.0", "x"),
    (two_pass_variance, "f(xs) == f(xs)", "xs"),
    (rms, "f(signal) == f(signal)", "signal"),
]


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, law, seq", STUMBLES,
                         ids=[f"{fn.__name__}: {law}" for fn, law, _ in STUMBLES])
def test_the_mathematics_stands_over_non_empty_lists(fn, law, seq):
    (p,) = check_conjectures(fn, [claim(law, route="derive")])
    assert p.verdict == "proven", (law, p.verdict, p.sketch)


@pytest.mark.parametrize("fn, law, seq", STUMBLES,
                         ids=[f"{fn.__name__}: {law}" for fn, law, _ in STUMBLES])
def test_the_empty_input_line_is_falsified_with_its_witness(fn, law, seq):
    probes = check_conjectures(fn, [claim(law)], float_companions=True)
    head = probes[0]
    line = next(p for p in probes if p.name == f"is_empty_safe[{seq}]")
    assert line.verdict == "falsified", (law, line.verdict, line.note)
    assert line.counterexample.startswith(f"{seq} = []"), \
        line.counterexample
    assert line.meta["mathema.companion_of"] == head.name
    assert head.verdict == "falsified", (law, head.verdict)
    assert head.counterexample == line.counterexample


@pytest.mark.parametrize("fn, law, seq", [
    (guarded_ema, "for alpha in [0, 1], f(x, 1.0) == x[-1]", "x"),
    (total, "f(xs) == f(xs)", "xs"),
])
def test_a_guarded_or_returning_function_keeps_its_claim(fn, law, seq):
    probes = check_conjectures(fn, [claim(law)], float_companions=True)
    head = probes[0]
    line = next(p for p in probes if p.name == f"is_empty_safe[{seq}]")
    assert line.verdict == "holds", (line.verdict, line.note)
    assert head.verdict in ("proven", "holds"), (head.verdict, head.note)


def test_a_fixed_length_has_no_empty_input_line():
    probes = check_conjectures(ema, [claim("for x in R^3, f(x, 1.0) == x[-1]")],
                               float_companions=True)
    assert not [p for p in probes if p.name.startswith("is_empty_safe")]
    assert probes[0].verdict == "proven", probes[0].note


def test_a_claim_falsified_on_non_empty_lists_keeps_its_own_witness():
    probes = check_conjectures(ema, [claim("f(x, alpha) == x[-1]")],
                               float_companions=True)
    head = probes[0]
    assert head.verdict == "falsified"
    assert not head.counterexample.startswith("x = []"), head.counterexample
    line = next(p for p in probes if p.name == "is_empty_safe[x]")
    assert line.verdict == "falsified"
