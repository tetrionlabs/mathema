# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A write outside the call falsifies `is_state_safe(f)` in general. A
write in a branch proven unreachable over the claim's domain never
runs, so there the function is proven state safe, and the row names
the unreachable code and how it was shown unreachable: a test that is
the constant False, or one solved exactly to hold nowhere in the
domain, missing values included. A branch only sampled, or reachable
at a missing value the domain admits, is not shown unreachable, and
the write falsifies as in general. The same holds for
`is_deterministic(f)`."""
from mathema.conjecture import check_conjectures, claim

_log: list = []


def never_writes(x):
    if False:
        _log.append(x)
    return x * 2.0


def writes_past_ten(x: float) -> float:
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def writes_in_the_else(x: float) -> float:
    if x < 10.0:
        return x
    else:
        _log.append(x)
    return x


def writes_past_a_half(x: float) -> float:
    if x > 0.5:
        _log.append(x)
    return x


def writes_past_y(x: float, y: float) -> float:
    if x > y + 10.0:
        _log.append(x)
    return x


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


def test_a_write_under_a_constant_false_test_is_proven_state_safe():
    for text in ("for x in [0, 1], is_state_safe(f)", "is_state_safe(f)"):
        p = _row(never_writes, text)
        assert p.verdict == "proven", (text, p.verdict, p.sketch)
        assert "unreachable code" in p.sketch, p.sketch
        assert "constant" in p.sketch, p.sketch


def test_a_write_in_a_branch_solved_to_hold_nowhere_is_proven_state_safe():
    p = _row(writes_past_ten, "for x in [0, 1], is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "unreachable code" in p.sketch and "x > 10" in p.sketch, p.sketch


def test_a_write_under_a_constant_false_test_is_proven_deterministic():
    p = _row(never_writes, "for x in [0, 1], is_deterministic(f)")
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert "unreachable code" in p.sketch, p.sketch


def test_a_branch_a_missing_value_takes_is_not_unreachable():
    # nan < 10 is False, so nan, which the float domain admits, runs the else
    p = _row(writes_in_the_else, "for x in [0, 5], is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch)


def test_a_reachable_branch_still_falsifies():
    p = _row(writes_past_a_half, "for x in [0, 1], is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert "unreachable" not in (p.counterexample or ""), p.counterexample


def test_a_branch_not_shown_unreachable_still_falsifies():
    p = _row(writes_past_y, "for x in [0, 1], y in [0, 1], is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.sketch)
