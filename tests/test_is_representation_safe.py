# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""is_representation_safe[param]: the machine representation of a
mathematical value must not change the implementation's behaviour
beyond what the declared domain's representation policy sanctions.
Deliberately not what mypy checks: mypy proves static name-level type
consistency without running anything; this claim runs the code and
adjudicates whether f(2), f(2.0), and f(True) AGREE, per the
value-typed domain policy (Z admits machine ints only)."""
from mathema.analysis import analyze_source
from mathema.conjecture import check_conjectures, claim
from mathema.suggest import suggest_claims


def counts(t: int) -> float:
    return float(sum(range(t)))


def halved(x: float) -> float:
    return x / 2.0


def int_hostile(x: float) -> float:
    if isinstance(x, int):
        raise TypeError("floats only")
    return x / 2.0


def disciplined(n: int) -> int:
    if isinstance(n, bool) or not isinstance(n, int):
        raise TypeError("a machine int is required")
    return n * 2


def _one(fn, law, route="best", domain=None):
    (probe,) = check_conjectures(fn, [claim(law, route=route)],
                                 domain=domain, facts=analyze_source(fn))
    return probe


def test_divergence_across_spellings_falsifies_with_the_pair():
    # range(t) needs a machine int: over an R-typed domain both
    # spellings of 3 are admitted, and the float spelling raises
    probe = _one(counts, "is_representation_safe(t)",
                 domain={"t": (0.0, 10.0)})
    assert probe.verdict == "falsified"
    assert probe.route == "probe:algorithmic"
    assert "float spelling" in probe.counterexample
    assert "raised TypeError" in probe.counterexample


def test_agreeing_spellings_hold():
    # x / 2.0 treats 3, 3.0, and True == 1 identically: every admitted
    # spelling returns the same mathematical value
    probe = _one(halved, "is_representation_safe(x)",
                 domain={"x": (0.0, 10.0)})
    assert probe.verdict == "holds"
    assert probe.n > 0


def test_guard_rejecting_an_admitted_spelling_disproves_structurally():
    # the domain admits both spellings of 2; the body's raising type
    # guard rejects the int one, structural disproof, corroborated
    # by the real call as its witness
    probe = _one(int_hostile, "is_representation_safe(x)",
                 domain={"x": (0.0, 10.0)})
    assert probe.verdict == "falsified"
    assert probe.route == "examine"
    assert "type guard" in probe.counterexample


def test_complete_integer_discipline_proves_structurally():
    # an integer-typed domain admits exactly one machine spelling, and
    # the guards enforce it completely: int accepted, bool explicitly
    # rejected (isinstance(n, int) alone would let True through)
    probe = _one(disciplined, "is_representation_safe(n)",
                 domain={"n": "Z"})
    assert probe.verdict == "proven"
    assert probe.route == "examine"
    assert "exactly one machine spelling" in probe.sketch


def test_an_excluded_spelling_must_keep_the_declared_return_type():
    # the int annotation leaves 2.0 outside the domain; the float
    # spelling is judged on agreement with f(2) and on the return type f
    # declares: 4.0 agrees in value but is no int
    def loose_double(n: int) -> int:
        return n * 2
    probe = _one(loose_double, "is_representation_safe(n)")
    assert probe.verdict == "falsified"
    assert "returned" in probe.counterexample
    assert "(float) where f declares -> int" in probe.counterexample, \
        probe.counterexample


def test_an_excluded_spelling_that_agrees_holds_without_a_declared_int():
    def untyped_double(n: int):
        return n * 2

    def float_double(n: int) -> float:
        return n * 2
    for fn in (untyped_double, float_double):
        probe = _one(fn, "is_representation_safe(n)")
        assert probe.verdict == "holds", (fn.__name__, probe.counterexample)


def test_an_excluded_spelling_that_disagrees_falsifies():
    def typed_half(n: int) -> float:
        return n / 2 if isinstance(n, int) else -1.0
    probe = _one(typed_half, "is_representation_safe(n)")
    assert probe.verdict == "falsified"
    assert "diverges across machine spellings" in probe.counterexample


def test_suggested_only_where_types_are_structural():
    typed = {c.name for c in suggest_claims(counts)}
    assert "is_representation_safe[t]" in typed

    def bare(a):
        return a + 1.0
    untyped = {c.name for c in suggest_claims(bare)}
    assert not any(n.startswith("is_representation_safe") for n in untyped)
