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


def refuses_by_one_compound_guard(x: float) -> float:
    if x < 0 or x >= 0:
        raise ValueError("x is refused")
    return x


def refuses_by_magnitude(x: float) -> float:
    if abs(x) >= 0:
        raise ValueError("x is refused")
    return x


def refuses_every_order(x: float, y: float) -> float:
    if x < y:
        raise ValueError("x is below y")
    if x >= y:
        raise ValueError("x is not below y")
    return 0.0


def refuses_every_sum(x: float, y: float) -> float:
    if x + y < 0:
        raise ValueError("the sum is negative")
    if x + y >= 0:
        raise ValueError("the sum is not negative")
    return 0.0


def leaves_the_diagonal(x: float, y: float) -> float:
    if x < y:
        raise ValueError("x is below y")
    if x > y:
        raise ValueError("x is above y")
    return 0.0


def legacy_rate(tenor: float) -> float:
    raise NotImplementedError("legacy_rate is retired")


def _rows(fn, text):
    rec = mathema.check(fn, claims=[text])
    stem = claim(text).name
    rows = [p for p in rec.probes if p.name.startswith(stem)]
    assert rows, [p.name for p in rec.probes]
    return rows


def _no_valid_domain_on_every_line(fn, text, refused=None):
    rows = _rows(fn, text)
    for p in rows:
        assert p.verdict == "unknown", (p.name, p.verdict, p.counterexample,
                                        p.note)
        assert p.counterexample is None, (p.name, p.counterexample)
        assert "no valid domain" in (p.note or ""), (p.name, p.note)
        if refused is not None:
            assert f"f's own guard raises where {refused}" \
                in (p.note or ""), (p.name, p.note)
    return rows


def test_a_compound_guard_refusing_every_input_has_no_valid_domain():
    _no_valid_domain_on_every_line(refuses_by_one_compound_guard,
                                   "f(x) >= 0", "x < 0 or x >= 0")
    _no_valid_domain_on_every_line(refuses_by_magnitude, "f(x) >= 0",
                                   "abs(x) >= 0")


def test_two_parameter_guards_refusing_every_input_have_no_valid_domain():
    rows = _no_valid_domain_on_every_line(refuses_every_order,
                                          "f(x, y) >= 0", "x < y or x >= y")
    # the mathematics line and the computation line are both in the record
    assert {p.name for p in rows} >= {"f_x_y_ge_0", "f_x_y_ge_0[float]"}, \
        [p.name for p in rows]
    _no_valid_domain_on_every_line(refuses_every_sum, "f(x, y) >= 0",
                                   "x + y < 0 or x + y >= 0")


def test_two_parameter_guards_leaving_a_line_keep_a_working_domain():
    for p in _rows(leaves_the_diagonal, "f(x, y) >= 0"):
        assert "no valid domain" not in (p.note or ""), (p.name, p.note)
        assert p.verdict in ("proven", "holds"), (p.name, p.verdict,
                                                  p.counterexample, p.note)


def test_a_stated_domain_on_two_parameters_still_falsifies():
    (p,) = check_conjectures(refuses_every_order, [claim(
        "for x in [0, 1], y in [0, 1], f(x, y) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "no valid domain" not in (p.note or ""), p.note


def test_a_body_that_only_raises_has_no_valid_domain():
    _no_valid_domain_on_every_line(legacy_rate, "f(tenor) >= 0")
    (p,) = check_conjectures(legacy_rate, [claim("is_defined(f)")])
    assert p.verdict == "unknown", (p.verdict, p.note)
    assert "no valid domain" in (p.note or ""), p.note


def test_a_stated_domain_on_a_body_that_only_raises_still_falsifies():
    (p,) = check_conjectures(legacy_rate,
                             [claim("for tenor in [1, 2], f(tenor) >= 0")])
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_is_defined_over_guards_refusing_every_input_has_no_valid_domain():
    for fn in (refuses_every_order, refuses_every_sum,
               refuses_by_one_compound_guard, refuses_by_magnitude):
        (p,) = check_conjectures(fn, [claim("is_defined(f)")])
        assert p.verdict == "unknown", (fn.__name__, p.verdict, p.note)
        assert "no valid domain" in (p.note or ""), (fn.__name__, p.note)
