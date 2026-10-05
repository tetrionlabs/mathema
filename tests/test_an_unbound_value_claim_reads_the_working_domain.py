# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim that binds no domain for a parameter is judged over
the function's working domain: what its annotations admit, minus what
its own guards refuse. A guard raising where x < 0 leaves x >= 0, and
the claim is proven there; the record says what the working domain is,
and the statement stays as written. A domain the claim states is never
narrowed: a raise inside it falsifies. A definedness falsification
found by executing f at a point its computed region suggests reports
that mechanism as its route."""
import math
import re

from mathema.conjecture import check_conjectures, claim


def guarded_neg(x: float) -> float:
    if x < 0:
        raise ValueError("x is negative")
    return math.sqrt(x)


def _one(law):
    (p,) = check_conjectures(guarded_neg, [claim(law)])
    return p


def test_an_unbound_claim_is_proven_over_what_the_guard_leaves():
    for law in ("f(x) >= 0", "f(x) * f(x) == x"):
        p = _one(law)
        assert p.verdict == "proven", (law, p.verdict, p.sketch, p.note)
        assert "for x" not in p.statement, p.statement
        assert "the working domain is x in [0, oo)" in (p.note or ""), p.note
        assert (p.meta or {}).get("mathema.working_domain", {}).get("x") \
            == "[0, oo)", p.meta


def test_a_stated_domain_is_never_narrowed():
    p = _one("for x in [-2, -1], f(x) >= 0")
    assert p.verdict == "falsified", (p.verdict, p.note)


def arcsine(x: float) -> float:
    return math.asin(x)


def test_an_executed_definedness_witness_is_reported_by_its_mechanism():
    # the region is computed, the witness executed: the route says so
    # whatever the claim is named
    for name in (None, "c"):
        (p,) = check_conjectures(arcsine, [claim(
            "for x in [-2, 2], is_defined(f)", name=name)])
        assert p.verdict == "falsified", (name, p.verdict)
        assert p.route == "probe:semi_analytical", (name, p.route)


def ordered_gap(x: float, y: float) -> float:
    if x > y:
        raise ValueError("x must not exceed y")
    return y - x


def outside_unit(x: float) -> float:
    if -1 < x < 1:
        raise ValueError("x is inside (-1, 1)")
    return abs(x)


def test_a_two_parameter_guard_leaves_a_working_domain_with_no_witness_in_it():
    (p,) = check_conjectures(ordered_gap, [claim("f(x, y) >= 0")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert "the domain left by f's guards (x > y)" in (p.note or ""), p.note
    (p,) = check_conjectures(ordered_gap, [claim(
        "for x in [0, 1], y in [0, 1], f(x, y) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_guard_leaving_a_union_reads_the_union():
    (p,) = check_conjectures(outside_unit, [claim("f(x) >= 1")])
    assert p.verdict in ("proven", "holds"), (p.verdict, p.counterexample,
                                              p.note)
    assert "x in (-oo, -1] ∪ [1, oo)" in (p.note or ""), p.note


def test_the_probe_counts_the_draws_the_guard_refused():
    (p,) = check_conjectures(outside_unit, [claim("f(x) >= 1", route="probe")])
    assert p.verdict == "holds", (p.verdict, p.counterexample, p.note)
    assert re.search(r"\d+ draws? refused by f's own guard", p.note or ""), \
        p.note


def capped_root(x: float) -> float:
    if x > 5:
        raise ValueError("x is above 5")
    return math.sqrt(x)


def test_a_raise_inside_the_working_domain_still_falsifies():
    # the guard leaves x <= 5, where math.sqrt still raises for x < 0:
    # that raise is no refusal of f's own, and it is a counterexample
    (p,) = check_conjectures(capped_root, [claim("f(x) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("x = -"), p.counterexample
