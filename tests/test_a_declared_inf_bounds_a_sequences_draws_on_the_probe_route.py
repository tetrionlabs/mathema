# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""`let |inf| be B` bounds what the probe route executes along every
unbounded direction, a sequence's elements included: the magnitude
corners it meets for a list (the cancelling pairs, the range's ends)
and its random draws run to B and no further, as a scalar's do. A
declared finite end is the claim's own and stays. The lists here exclude
the missing value, so every call is a draw of the claim (a missing
input's policy is read by calls of its own, with filled values)."""
import math

from mathema.conjecture import check_conjectures, claim

SEEN: list = []


def walk_total(xs: list, y0: float) -> float:
    SEEN.extend(abs(v) for v in xs)
    total = y0
    i = 0
    while i < len(xs):
        total = xs[i] + total
        i += 1
    return total


def largest_seen(xs: list, y0: float) -> float:
    SEEN.extend(abs(v) for v in xs if isinstance(v, (int, float)))
    SEEN.append(abs(y0))
    return 0.0


def _largest(fn, statement: str) -> tuple:
    SEEN.clear()
    (p,) = check_conjectures(fn, [claim(statement, route="probe")])
    finite = [v for v in SEEN if math.isfinite(v)]
    return p, max(finite)


def test_a_list_over_the_whole_line_is_drawn_inside_the_declared_inf():
    _p, top = _largest(largest_seen,
                       "let |inf| be 1e7, for xs in R^n \\ {missing}, "
                       "y0 in [-10, 10], f(xs, y0) == 0")
    assert top <= 1e7, top


def test_a_declared_finite_end_is_kept():
    # the float nearest 1e30 is 1.0000000000000000199e30, past 10**30 as
    # written, so the end drawn is the float just inside it
    _p, top = _largest(largest_seen,
                       "let |inf| be 1e7, for xs in [-1e30, 1e30]^n \\ "
                       "{missing}, y0 in [-10, 10], f(xs, y0) == 0")
    assert top == math.nextafter(1e30, 0), top


def test_without_a_declared_inf_the_draws_reach_far_past_it():
    _p, top = _largest(largest_seen, "for xs in R^n \\ {missing}, "
                                     "y0 in [-10, 10], f(xs, y0) == 0")
    assert top > 1e16, top


def _witness_elements(p) -> list:
    xs, _y0 = p.meta["mathema.counterexample_args"]
    return [abs(v) for v in xs if isinstance(v, (int, float))]


def test_an_unbound_list_is_not_falsified_past_the_declared_inf():
    # without the binding the probe meets the cancelling pair at 1e16
    (wide,) = check_conjectures(walk_total, [claim(
        "for y0 in [-10, 10], f(xs, y0) == f(xs, 0) + y0", route="probe")])
    assert wide.verdict == "falsified"
    assert max(_witness_elements(wide)) > 1e7, wide.counterexample
    (p,) = check_conjectures(walk_total, [claim(
        "let |inf| be 1e7, for y0 in [-10, 10], f(xs, y0) == f(xs, 0) + y0",
        route="probe")])
    # sums of eight elements within 1e7 keep y0 to the allowance
    assert p.verdict == "holds", p.counterexample


def test_a_probe_only_line_is_offered_the_binding_its_run_holds_under():
    import mathema
    rec = mathema.check(walk_total, claims=[mathema.claim(
        "for y0 in [-10, 10], f(xs, y0) == f(xs, 0) + y0", name="law")])
    (line,) = [p for p in rec.probes if p.name == "law"]
    assert line.route == "probe" and line.verdict == "falsified"
    offer = line.meta["mathema.infinity_offer"]["words"]
    (held,) = check_conjectures(walk_total, [claim(
        f"{offer}, for y0 in [-10, 10], f(xs, y0) == f(xs, 0) + y0",
        route="probe")])
    assert held.verdict == "holds", held.counterexample
