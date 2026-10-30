# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A declared tolerance binds the computation line only. On route derive
the probe falsifies the mathematics: a draw that passes only within the
declared tolerance is decided again on the body read exactly, and where
it is false there it falsifies the claim. On the default route the probe
is the computation line, and the tolerance admits the draw."""
import pytest

from mathema.conjecture import check_conjectures, claim


def loop_nudge(x: float) -> float:
    # x + 1e-10, by a loop derive does not lift
    t = x
    i = 0
    while i < 1:
        t = t + 1e-10
        i += 1
    return t


@pytest.mark.parametrize("law", ["for x in [1, 2], f(x) == x",
                                 "for x in [1, 2], f(x) <= x"])
def test_a_pass_within_the_tolerance_is_decided_exactly_on_derive(law):
    # f(x) = x + 1e-10 exactly, never equal to x, never below it
    (p,) = check_conjectures(loop_nudge, [claim(law, route="derive",
                                                tolerance=1e-9)])
    assert p.verdict == "falsified", (p.verdict, p.route, p.note)
    assert "false here in exact arithmetic" in p.counterexample, p.counterexample


@pytest.mark.parametrize("law", ["for x in [1, 2], f(x) == x",
                                 "for x in [1, 2], f(x) <= x"])
def test_the_tolerance_admits_the_computation_on_the_probe(law):
    (p,) = check_conjectures(loop_nudge, [claim(law, route="probe",
                                                tolerance=1e-9)])
    assert p.verdict == "holds", (p.verdict, p.note)
