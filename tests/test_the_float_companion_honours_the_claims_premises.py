# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The `[float]` companion of a proof executes the claim over the same
points the proof quantifies over: under `assuming f is defined` it never
executes a point the premise leaves out, so it cannot falsify the
computation there."""
import math

import pytest

from mathema.conjecture import check_conjectures, claim


def root(x: float) -> float:
    return math.sqrt(x)


def root_of_difference(x: float, y: float) -> float:
    return math.sqrt(x - y) + (x - y)


def _companion(probes):
    return next(p for p in probes if p.name.endswith("[float]"))


@pytest.mark.needs_full_proof_budget
@pytest.mark.parametrize("fn, text", [
    (root, "assuming f is defined, for x in [-1, 1], f(x) >= 0"),
    (root, "assuming is_defined(f), for x in [-1, 1], f(x) >= 0"),
    (root_of_difference,
     "assuming f is defined, for x in [-1, 1], y in [-1, 1], f(x, y) >= 0"),
])
def test_the_companion_skips_the_points_the_definedness_premise_excludes(
        fn, text):
    probes = check_conjectures(fn, [claim(text, route="derive")],
                               float_companions=True)
    assert probes[0].verdict == "proven", (probes[0].verdict,
                                           probes[0].sketch)
    companion = _companion(probes)
    assert companion.verdict == "holds", (companion.verdict,
                                          companion.counterexample,
                                          companion.sketch)


@pytest.mark.needs_full_proof_budget
def test_the_companion_still_executes_the_points_the_premise_admits():
    def overflowing(x: float) -> float:
        return math.sqrt(x) * math.exp(x)

    probes = check_conjectures(overflowing, [
        claim("assuming f is defined, for x in [-1, 1000], f(x) >= 0",
              route="derive")], float_companions=True)
    companion = _companion(probes)
    assert companion.verdict == "falsified", (companion.verdict,
                                              companion.sketch)
    found = float(companion.counterexample.split("=")[1])
    assert found >= 0
