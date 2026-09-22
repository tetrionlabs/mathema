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


def test_annotation_inferred_policy_rejects_the_unenforced_float():
    # the int annotation infers a Z-typed domain; the float spelling
    # of an admitted integer is policy-excluded, but sum(range(3.0))
    # raising is exactly the enforcement Z demands, while a body
    # that silently ACCEPTS the float spelling falsifies
    def loose_double(n: int) -> int:
        return n * 2
    probe = _one(loose_double, "is_representation_safe(n)")
    assert probe.verdict == "falsified"
    assert "asserted, not enforced" in probe.counterexample


def test_suggested_only_where_types_are_structural():
    typed = {c.name for c in suggest_claims(counts)}
    assert "is_representation_safe[t]" in typed

    def bare(a):
        return a + 1.0
    untyped = {c.name for c in suggest_claims(bare)}
    assert not any(n.startswith("is_representation_safe") for n in untyped)
