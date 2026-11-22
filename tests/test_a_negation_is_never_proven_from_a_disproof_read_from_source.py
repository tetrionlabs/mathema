# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A positive claim falsified by reading the source names a line, not
a call that ran. That line may sit in a branch no call reaches
(`if False:`, or a condition the domain never meets), so the negation
of such a claim is never proven from it: it is unknown, with the
reason. A negation is proven from a disproof only when the disproof's
witness was executed."""
import pytest

from mathema.conjecture import check_conjectures, claim

_log: list = []


def never_writes(x):
    if False:
        _log.append(x)
    return x * 2.0


def writes_past_ten(x):
    if x > 10.0:
        _log.append(x)
    return x * 2.0


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


@pytest.mark.parametrize("fn", [never_writes, writes_past_ten])
@pytest.mark.parametrize("text", [
    "for x in [0, 1], not is_state_safe(f)",
    "for x in [0, 1], not is_deterministic(f)",
    "not is_state_safe(f)",
])
def test_a_negation_read_from_an_unexecuted_line_is_not_proven(fn, text):
    p = _row(fn, text)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


def test_the_negation_says_why_it_is_not_decided():
    p = _row(never_writes, "for x in [0, 1], not is_state_safe(f)")
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch)
    assert "not executed" in (p.note or ""), p.note


def test_a_function_that_writes_is_still_not_state_safe():
    def appends(x):
        _log.append(x)
        return x
    p = _row(appends, "for x in [0, 1], is_state_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.route, p.sketch)


def test_a_pure_function_is_still_proven_state_safe():
    def doubled(x):
        return x * 2.0
    p = _row(doubled, "for x in [0, 1], is_state_safe(f)")
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
