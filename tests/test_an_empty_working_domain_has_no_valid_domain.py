# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A bare family claim is judged over the function's working domain:
the inputs its annotations and binding admit, minus what its own guards
refuse. When the guards refuse every input, nothing is left to judge,
and the claim is unknown with the reason "no valid domain", never a
proof over nothing."""
from mathema import enforce_domain
from mathema.conjecture import check_conjectures, claim


def refuses_everything(x: float) -> float:
    if x == x:
        raise ValueError("x is refused")
    raise ValueError("x is refused")


def refuses_negatives(x: float) -> float:
    if x < 0:
        raise ValueError("x is negative")
    return x + 1.0


def test_every_input_refused_is_unknown_with_no_valid_domain():
    (p,) = check_conjectures(refuses_everything, [claim("is_defined(f)")])
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)
    assert "no valid domain" in (p.note or ""), p.note


def test_a_guard_that_leaves_a_domain_still_proves():
    (p,) = check_conjectures(refuses_negatives, [claim("is_defined(f)")])
    assert p.verdict == "proven", (p.verdict, p.note)


@enforce_domain(domain={"x": (0, 1)})
def unit_only(x: float) -> float:
    return x + 1.0


def cut_both_sides(x: float) -> float:
    if x < 0:
        raise ValueError("x is negative")
    if x >= 0:
        raise ValueError("x is not negative")
    return x


def test_a_binding_outside_the_enforced_domain_has_no_valid_domain():
    (p,) = check_conjectures(unit_only,
                             [claim("for x in [2, 3], is_defined(f)")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "no valid domain" in (p.note or ""), p.note


def test_guards_that_cut_the_whole_line_leave_no_valid_domain():
    (p,) = check_conjectures(cut_both_sides, [claim("is_defined(f)")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "no valid domain" in (p.note or ""), p.note
