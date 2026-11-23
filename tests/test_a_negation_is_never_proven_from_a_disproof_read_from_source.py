# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A positive claim falsified by reading the source names a line, not
a call that ran: a write in a branch the domain reaches is read, never
executed. The negation of such a claim is never proven from it: it is
unknown, with the reason. A negation is proven from a disproof only
when the disproof's witness was executed, and a positive proven (a
write only in unreachable code) falsifies it."""
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


def writes_past_a_half(x):
    if x > 0.5:
        _log.append(x)
    return x * 2.0


def _row(fn, text):
    rows = check_conjectures(fn, [claim(text)])
    return next(r for r in rows if not r.name.endswith("[float]"))


WITNESSED = [
    (writes_past_a_half, "for x in [0, 1], not is_state_safe(f)"),
    (writes_past_a_half, "not is_state_safe(f)"),
    (writes_past_ten, "not is_state_safe(f)"),
]
UNEXECUTED = [(fn, text)
              for fn in (never_writes, writes_past_ten, writes_past_a_half)
              for text in ("for x in [0, 1], not is_state_safe(f)",
                           "for x in [0, 1], not is_deterministic(f)",
                           "not is_state_safe(f)")
              if (fn, text) not in WITNESSED]


@pytest.mark.parametrize("fn, text", UNEXECUTED)
def test_a_negation_read_from_an_unexecuted_line_is_not_proven(fn, text):
    p = _row(fn, text)
    assert p.verdict != "proven", (p.verdict, p.route, p.sketch)


@pytest.mark.parametrize("fn, text", WITNESSED)
def test_a_negation_is_proven_by_a_call_that_ran_and_wrote(fn, text):
    p = _row(fn, text)
    assert p.verdict == "proven", (p.verdict, p.route, p.sketch)
    assert "proven by a witness: the call at x = " in p.sketch, p.sketch
    assert "was run" in p.sketch and "_log" in p.sketch, p.sketch


def test_the_negation_says_why_it_is_not_decided():
    p = _row(writes_past_a_half, "for x in [0, 1], not is_deterministic(f)")
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
