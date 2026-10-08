# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""An `is_defined` claim falsified by a call executed at a candidate
point the computed region suggested is decided by that execution: its
route is a probe route, never the structural `examine`. A proof of the
same claim, decided from the body's structure, stays `examine`."""
import math

from mathema.conjecture import check_conjectures, claim


def atanh_of(x: float) -> float:
    return math.atanh(x)


def smooth(x: float) -> float:
    return math.exp(x) + math.sin(x)


def test_a_falsified_is_defined_names_the_executed_route():
    (p,) = check_conjectures(atanh_of, [
        claim("for x in [-2, 2], is_defined(f)", route="derive")])
    assert p.verdict == "falsified", (p.verdict, p.sketch)
    assert (p.meta or {}).get("mathema.corroboration") == "reproduced"
    assert p.route.startswith("probe"), p.route


def test_a_proven_is_defined_stays_examine():
    (p,) = check_conjectures(smooth, [
        claim("for x in [-2, 2], is_defined(f)", route="derive")])
    assert p.verdict == "proven", (p.verdict, p.sketch)
    assert p.route == "examine", p.route
