# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim's empty-input line calls f the way the claim does: with
`f(x, alpha=1.0)`, `f(x, sqrt(1.0))`, `f(x[:], 1.0)` or a call through
a bound function, each call's arguments are evaluated as the claim
evaluates them, at `x = []`, and f executed there; an unguarded raise
falsifies the line and the claim, and the witness names the arguments
of that call. A call that cannot bind to f's signature is a
misspecified claim, never a witness and never unknown.
"""
from __future__ import annotations

import pytest

from mathema.claims import check_conjectures, claim


def ema(x: list, alpha: float) -> float:
    y = x[0]
    for v in x[1:]:
        y = alpha * v + (1 - alpha) * y
    return y


@pytest.mark.parametrize("law", [
    "f(x, alpha=1.0) == x[-1]",
    "f(x, sqrt(1.0)) == x[-1]",
    "f(x, abs(-1.0)) == x[-1]",
    "f(x[:], 1.0) == x[-1]",
])
def test_a_raising_call_at_the_empty_list_falsifies(law):
    for route in ("derive", "best"):
        probes = check_conjectures(ema, [claim(law, route=route)],
                                   float_companions=True)
        line = next(p for p in probes if p.name == "is_empty_safe[x]")
        assert line.verdict == "falsified", (law, route, line.verdict,
                                             line.note)
        assert line.counterexample == "x = [], alpha = 1.0", \
            line.counterexample
        assert probes[0].verdict == "falsified", (law, probes[0].verdict)


@pytest.mark.parametrize("law", ["f(x) == x[-1]", "f(x, 1.0, 2.0) == x[-1]"])
def test_a_call_that_does_not_bind_is_misspecified(law):
    (p,) = check_conjectures(ema, [claim(law, route="derive")])
    assert p.verdict == "skipped:misspecified", (law, p.verdict, p.note)


def test_a_call_through_a_bound_function_is_read():
    for route in ("derive", "best"):
        probes = check_conjectures(ema, [claim(
            "let g = math.fabs, f(x, g(1.0)) == x[-1]", route=route)],
            float_companions=True)
        line = next(p for p in probes if p.name == "is_empty_safe[x]")
        assert line.verdict == "falsified", (route, line.verdict, line.note)
        assert line.counterexample == "x = [], alpha = 1.0", \
            line.counterexample
