# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_empty_safe[xs]: the empty-sequence boundary is handled, not
stumbled into; min/max/mean of [] raise however sound the maths.
An explicit raising emptiness guard is deliberate rejection (safe,
provable structurally); an unguarded raise on [] is an accidental
crash and falsifies with that witness."""
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def guarded_mean(xs: list) -> float:
    if not xs:
        raise ValueError("mean of an empty sequence")
    return sum(xs) / len(xs)


def naive_mean(xs: list) -> float:
    return sum(xs) / len(xs)


def total(xs: list) -> float:
    return float(sum(xs))


def _one(fn, law, route="best"):
    (probe,) = check_conjectures(fn, [claim(law, route=route)],
                                 facts=analyze_source(fn))
    return probe


def test_explicit_guard_proves_deliberate_rejection():
    probe = _one(guarded_mean, "is_empty_safe(xs)")
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "deliberately rejected" in probe.sketch


def test_unguarded_empty_crash_falsifies_with_the_witness():
    probe = _one(naive_mean, "is_empty_safe(xs)")
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "xs = [] raised ZeroDivisionError" in probe.counterexample
    assert "no emptiness guard" in probe.counterexample


def test_clean_empty_return_proves_exhaustively_for_one_param():
    # sum([]) is 0: the empty boundary returns a well-defined value,
    # and with a single parameter the one empty call IS the whole
    # hazard class, established, so proven even from trials
    probe = _one(total, "is_empty_safe(xs)")
    assert probe.verdict == "proven"
    assert probe.route == "probe:algorithmic"
    assert "exhaustive" in probe.sketch


def test_suggested_only_where_an_emptiness_guard_exists():
    guarded = {c.name for c in suggest_claims(guarded_mean)}
    assert "is_empty_safe[xs]" in guarded
    unguarded = {c.name for c in suggest_claims(naive_mean)}
    assert not any(n.startswith("is_empty_safe") for n in unguarded)


def test_deterministic_proves_by_construction_for_a_lifted_body():
    def line(x: float) -> float:
        return 3.0 * x + 2.0
    (probe,) = check_conjectures(
        line, [claim("f(x) == f(x)", name="is_deterministic",
                     route="best")],
        facts=analyze_source(line))
    assert probe.verdict == "proven"
    assert "deterministic by construction" in probe.sketch


def test_deterministic_falls_to_the_empirical_loop_for_stateful_bodies():
    import random as _random

    def jittery(x: float) -> float:
        return x + _random.random()
    (probe,) = check_conjectures(
        jittery, [claim("f(x) == f(x)", name="is_deterministic",
                        route="best")],
        facts=analyze_source(jittery))
    assert probe.verdict == "falsified"
    # the generic empirical loop (not the family battery) decided this
    assert probe.route == "probe"
