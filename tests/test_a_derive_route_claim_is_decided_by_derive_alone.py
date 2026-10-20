# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim stated with route derive asks for derive alone: when derive
cannot settle it (a body it cannot read, a branch it cannot decide, a
timeout) the claim is unknown on the derive route, with derive's reason
in the note, and nothing runs the code for it. The default route, best,
still falls from derive to the probe."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim
from mathema.types import Vec

_ALONE = "the claim asks for the derive route alone, so the probe did not run"


def guarded(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x + 1


def piecewise(x: float) -> float:
    if x < 0:
        return -x
    return x * x


def head(xs: Vec("n")) -> float:
    return xs[0]


def paid(payment: float) -> float:
    total = 0.0
    month = 0
    while month < 12:
        total = total + payment * (1.01 ** month)
        month += 1
    return total


def double(x: float) -> float:
    return 2 * x


_UNSETTLED = [
    (guarded, "assuming x >= 5, for x in [-10, 10], f(x) >= 7"),
    (piecewise, "assuming x >= 1, for x in [-10, 10], f(x) >= 2"),
    (head, "f(xs) == xs[0]"),
    (paid, "for payment in [-10, 10], f(payment) >= -1000"),
    (paid, "for payment in [-10, 10], d(f(payment), payment) >= 0"),
    (paid, "for payment in [-10, 10], 0 <= f(payment) - f(payment) <= 1"),
]


@pytest.mark.parametrize("fn, text", _UNSETTLED)
def test_derive_alone_leaves_an_unsettled_claim_unknown(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c", route="derive")])
    assert (p.verdict, p.route) == ("unknown", "derive"), p
    assert _ALONE in p.note
    assert "the probe decided it" not in p.note
    assert "could not decide it either" not in p.note


def test_the_note_carries_derives_reason():
    (p,) = check_conjectures(head, [claim("f(xs) == xs[0]", name="c",
                                          route="derive")])
    assert "derive could not decide it (" in p.note
    assert p.meta["mathema.derive_status"] == "unliftable"
    assert p.meta["mathema.routes_attempted"].startswith(
        "routes attempted, derive: underivable")


@pytest.mark.parametrize("fn, text", _UNSETTLED[:4])
def test_the_default_route_still_falls_to_the_probe(fn, text):
    (p,) = check_conjectures(fn, [claim(text, name="c")])
    assert (p.route or "").startswith("probe"), p
    assert _ALONE not in (p.note or "")


def count_up(x: float) -> float:
    n = 0
    while n < x:
        n += 1
    return n


def ceiling_at_zero(x: float) -> float:
    return max(math.ceil(x), 0)


def test_an_equivalence_on_derive_alone_runs_no_sampled_rung():
    text = "for x in [-5, 5], f =:= g"
    (alone,) = check_conjectures(count_up, [claim(
        text, name="c", route="derive", funcs={"g": ceiling_at_zero})])
    assert alone.verdict == "unknown"
    assert alone.route != "probe"
    assert _ALONE in alone.note
    (best,) = check_conjectures(count_up, [claim(
        text, name="c", funcs={"g": ceiling_at_zero})])
    assert (best.verdict, best.route) == ("holds", "probe")


def test_a_decided_derive_claim_is_unchanged():
    (p,) = check_conjectures(double, [claim("for x in [-10, 10], f(x) == 2*x",
                                            name="c", route="derive")])
    assert (p.verdict, p.route) == ("proven", "derive")
    assert _ALONE not in (p.note or "")
