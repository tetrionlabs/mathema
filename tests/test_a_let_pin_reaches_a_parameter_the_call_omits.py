# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`let p be v` pins a parameter: a call to f that leaves `p` out is
made with `p = v`, as it is for a library function, so the witness of a
falsified claim shows the value f actually ran with. Here
`head_default(x)` runs with `alpha = 2` and `f(x) == 2 * x[0]` holds
over non-empty lists; `head_default([])` reads `x[0]` with no emptiness
guard, so the claim's empty-input line is falsified with the pinned
call as its witness, while a guarded twin holds.
"""
from __future__ import annotations

from mathema.claims import check_conjectures, claim


def head_default(x: list, alpha: float = 1.0) -> float:
    return x[0] * alpha


def guarded_head(x: list, alpha: float = 1.0) -> float:
    if not x:
        raise ValueError("x is empty")
    return x[0] * alpha


_PINNED = "let alpha be 2, f(x) == 2 * x[0]"


def test_a_pinned_parameter_the_call_omits_is_passed():
    (p,) = check_conjectures(guarded_head, [claim(_PINNED)])
    assert p.verdict in ("holds", "proven"), (p.verdict, p.counterexample,
                                              p.note)


def test_the_empty_input_line_executes_the_pinned_call():
    probes = check_conjectures(head_default, [claim(_PINNED)],
                               float_companions=True)
    head = probes[0]
    line = next(p for p in probes if p.name == "is_empty_safe[x]")
    assert line.verdict == "falsified", (line.verdict, line.note)
    assert line.counterexample == "x = [], alpha = 2", line.counterexample
    assert head.verdict == "falsified", (head.verdict, head.note)
    assert head.counterexample == line.counterexample


def test_the_unpinned_default_is_falsified_with_what_ran():
    (p,) = check_conjectures(head_default, [claim(
        "assuming len(x) >= 1, f(x) == 2 * x[0]")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "alpha" not in (p.counterexample or ""), p.counterexample
