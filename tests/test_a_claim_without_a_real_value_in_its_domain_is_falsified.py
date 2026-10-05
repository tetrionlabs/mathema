# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A claim that states its domain explicitly is wrong wherever its own
side has no real value there: `(sqrt(x) - 1)^2` and `log(x) + 100` have
none for negative x. Such a point is never dropped as an unusable draw;
the claim is falsified with that point as its witness and a note saying
the claim's side has no real value there."""
import pytest

from mathema.conjecture import check_conjectures, claim


def zero(x: float) -> float:
    return 0.0


def _x(p):
    head = p.counterexample.split(":")[0].strip("()")
    return float(head.split("=")[-1])


@pytest.mark.parametrize("law", [
    "for x in [-1, 1], f(x) <= (sqrt(x) - 1)^2",
    "for x in [-1, -0.5], f(x) <= (sqrt(x) - 1)^2",
    "for x in [-1, 1], f(x) <= log(x) + 100",
])
def test_a_point_where_the_claim_has_no_real_value_falsifies_it(law):
    (p,) = check_conjectures(zero, [claim(law)])
    assert p.verdict == "falsified", (law, p.note)
    assert _x(p) <= 0
    assert "no real value" in p.counterexample


def test_a_claim_real_everywhere_on_its_domain_still_holds():
    (p,) = check_conjectures(zero, [claim("for x in [0, 1], f(x) <= (sqrt(x) - 1)^2")])
    assert p.verdict in ("holds", "proven")
