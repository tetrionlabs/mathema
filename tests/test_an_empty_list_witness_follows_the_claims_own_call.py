# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""When the claim admits the empty list and calls f at arguments of its
own (`f(x, alpha=1.0)`, `f(x, sqrt(1.0))`, `f(x[:], 1.0)`), each call is
evaluated as the claim evaluates it and f executed there; a raise is
the witness against the claim, and the witness names the arguments of
that call. A call that cannot bind to f's signature is a misspecified
claim, never a witness and never unknown.
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
        (p,) = check_conjectures(ema, [claim(law, route=route)])
        assert p.verdict == "falsified", (law, route, p.verdict, p.note)
        assert "x = []" in (p.counterexample or ""), p.counterexample
        assert "alpha = 1.0" in (p.counterexample or ""), p.counterexample


@pytest.mark.parametrize("law", ["f(x) == x[-1]", "f(x, 1.0, 2.0) == x[-1]"])
def test_a_call_that_does_not_bind_is_misspecified(law):
    (p,) = check_conjectures(ema, [claim(law, route="derive")])
    assert p.verdict == "skipped:misspecified", (law, p.verdict, p.note)
