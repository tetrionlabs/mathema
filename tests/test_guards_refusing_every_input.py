# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A value claim that binds no domain is read over the working domain
f's own guards leave. When those guards refuse every input, nothing is
left to judge: the claim is unknown with the reason "no valid domain"
on the mathematics line and the computation line alike, never a proof
over nothing and never a counterexample at a refused input. The note
describes the domain the guards leave, never calls the refused region
the working domain."""
import mathema
from mathema.conjecture import check_conjectures, claim


def nothing(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    if x >= 0:
        raise ValueError("nonneg")
    return x


def nonnegative_only(x: float) -> float:
    if x < 0:
        raise ValueError("neg")
    return x


def ordered_gap(x: float, y: float) -> float:
    if x > y:
        raise ValueError("x must not exceed y")
    return y - x


def test_a_value_claim_over_no_valid_domain_is_unknown():
    (p,) = check_conjectures(nothing, [claim("f(x) >= 0")])
    assert p.verdict == "unknown", (p.verdict, p.route, p.sketch, p.note)
    assert "no valid domain" in (p.note or ""), p.note
    assert "working domain is the domain left" not in (p.note or ""), p.note


def test_both_lines_of_the_record_are_unknown():
    rec = mathema.check(nothing, claims=["f(x) >= 0"])
    rows = [p for p in rec.probes if p.name.startswith("f_x_ge_0")]
    assert rows, rec.probes
    for p in rows:
        assert p.verdict == "unknown", (p.name, p.verdict, p.counterexample,
                                        p.note)
        assert p.counterexample is None, (p.name, p.counterexample)
        assert "no valid domain" in (p.note or ""), (p.name, p.note)


def test_the_probe_route_is_unknown_too():
    (p,) = check_conjectures(nothing, [claim("f(x) >= 0", route="probe")])
    assert p.verdict == "unknown", (p.verdict, p.counterexample, p.note)
    assert "no valid domain" in (p.note or ""), p.note


def test_a_stated_domain_the_guards_refuse_still_falsifies():
    (p,) = check_conjectures(nothing, [claim("for x in [1, 2], f(x) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_one_guard_states_the_domain_it_leaves():
    (p,) = check_conjectures(nonnegative_only, [claim("f(x) >= 0")])
    assert p.verdict == "proven", (p.verdict, p.note)
    assert "the working domain is x in [0, oo): f's own guard raises " \
        "where x < 0" in (p.note or ""), p.note


def test_a_two_parameter_guard_names_what_it_refuses_as_refused():
    (p,) = check_conjectures(ordered_gap, [claim("f(x, y) >= 0")])
    assert "f's own guard raises where x > y" in (p.note or ""), p.note
    assert "domain left by f's guards (x > y)" not in (p.note or ""), p.note
