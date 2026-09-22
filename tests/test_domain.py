# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
# --- an excluded region is not sampled ---------------------------------

def _spike(x):
    """One everywhere except a single spike down to zero at x = 1."""
    if x == 1.0:
        return 0.0
    return 1.0


def _pole(x):
    """Reciprocal of the distance from one."""
    return 1.0 / (x - 1.0)


def test_an_excluded_point_is_never_sampled():
    """`\\ {1}` removes a point from the region the claim is made over,
    so a trial must never land there; otherwise the exclusion is
    decoration and the claim is adjudicated over a wider region than it
    states. The control proves the test can see the point at all."""
    from mathema.claims import check_conjectures, claim

    excluded = check_conjectures(
        _spike, [claim("for x in [-1,1] \\ {1}, f(x) >= 1", route="probe")])[0]
    assert excluded.verdict == "holds", excluded.counterexample
    assert excluded.n and excluded.n > 10

    control = check_conjectures(
        _spike, [claim("for x in [-1,1], f(x) >= 1", route="probe")])[0]
    assert control.verdict == "falsified"
    assert "1" in (control.counterexample or "")


def test_an_excluded_pole_is_never_called():
    """The exclusion also has to hold for a point the function cannot
    be called at, a sampled x = 1 here raises rather than compares."""
    from mathema.claims import check_conjectures, claim

    probe = check_conjectures(
        _pole, [claim("for x in [-1,1] \\ {1}, f(x) != 0", route="probe")])[0]
    assert probe.verdict == "holds", probe.note


# --- the region a claim is adjudicated over must be exact -------------
#
# Three properties, each with a failure that actually happened:
#
#   1. A premise narrows the region as tightly as the equivalent domain
#      spelling. `assuming x > 0, for x in [-10,10]` used to reach only
#      `holds` where `for x in (0,10]` proved, because the premise
#      arrived after the symbols were built and the interval rung still
#      saw [-10, 10].
#   2. The narrowing is exact at the endpoint: a strict premise gives an
#      open endpoint, not a nearly-open one.
#   3. Narrowing never hides a real counterexample, a false claim
#      still falsifies, from a witness inside the assumed region.

def _recip(x):
    """Reciprocal."""
    return 1.0 / x


def _square(x):
    """Square."""
    return x * x


def _gap(a, b):
    """Difference."""
    return b - a


def _verdict(fn, law, route="derive"):
    from mathema.claims import check_conjectures, claim
    return check_conjectures(fn, [claim(law, route=route)])[0]


def test_a_premise_narrows_as_tightly_as_the_equivalent_domain():
    """The same region stated two ways must reach the same verdict;
    otherwise the premise spelling is second-class and a claim is
    refused over a region it never covered."""
    pairs = [
        (_recip, "for x in (0,10], f(x) > 0",
                 "assuming x > 0, for x in [-10,10], f(x) > 0"),
        (_recip, "for x in (0,5], f(x) > 0",
                 "assuming x > 0, for x in [-5,5], f(x) > 0"),
        (_square, "for x in [2,10], f(x) >= 4",
                  "assuming x >= 2, for x in [-10,10], f(x) >= 4"),
    ]
    for fn, by_domain, by_premise in pairs:
        stated = _verdict(fn, by_domain)
        assumed = _verdict(fn, by_premise)
        assert stated.verdict == assumed.verdict == "proven", (
            f"{by_premise!r} reached {assumed.verdict}, but the same region "
            f"as a domain reached {stated.verdict}")


def test_the_narrowed_region_is_reported_exactly():
    """`condition` says what was actually adjudicated, so a strict
    premise has to show an open endpoint, not a closed one."""
    probe = _verdict(_recip, "assuming x > 0, for x in [-10,10], f(x) > 0")
    assert "(0.0, 10.0]" in probe.condition, probe.condition
    assert "x > 0" in probe.statement, probe.statement

    non_strict = _verdict(_square, "assuming x >= 2, for x in [-10,10], f(x) >= 4")
    assert "[2.0, 10.0]" in non_strict.condition, non_strict.condition


def test_narrowing_never_hides_a_counterexample():
    """A premise restricts where the claim is made, never what may
    refute it inside that region."""
    false_in_region = _verdict(_recip, "assuming x > 0, for x in [-10,10], f(x) > 1")
    assert false_in_region.verdict == "falsified"
    assert false_in_region.counterexample

    also_false = _verdict(_square, "assuming x >= 2, for x in [-10,10], f(x) >= 100")
    assert also_false.verdict == "falsified"


def test_a_premise_relating_two_parameters_is_not_treated_as_a_box():
    """`a <= b` is not a rectangle, so it must reach the prover as an
    assumed gap rather than narrowing either parameter's interval."""
    ordered = _verdict(
        _gap, "assuming a <= b, for a in [-10,10], b in [-10,10], f(a,b) >= 0")
    assert ordered.verdict == "proven"
    assert "[-10.0, 10.0]" in ordered.condition, ordered.condition


def test_the_statement_is_always_self_contained_claim_grammar():
    """A probe's statement is the canonical text: it re-parses on its
    own to a claim with the same identity, no side channel needed.
    (`condition` still rides beside it as the region the evidence
    covered: display and provenance, never read back. A conjunction
    glyph once appeared in statement text and silently cost every
    conditional claim its docsync fingerprint, because the reparse
    failed and the old fingerprint helper returned None on failure;
    identity now raises on unparseable text instead.)"""
    from mathema.sync import _row_identity

    for law in ("assuming x > 0, for x in [-10,10], f(x) > 0",
                "assuming x >= 2, for x in [-10,10], f(x) >= 4",
                "for x in (0,10], f(x) > 0"):
        fn = _square if ">= 4" in law else _recip
        probe = _verdict(fn, law)
        assert probe.condition
        identity = _row_identity({"statement": probe.statement})
        assert identity is not None
        # and the identity is stable: re-parsing the statement and
        # re-rendering lands on the same string
        assert _row_identity({"statement": identity[0]}) == identity

def test_a_premise_and_its_domain_spelling_report_one_region():
    """The premise narrows the quantified interval itself, so the two
    spellings of one region render identically, not merely
    equivalently."""
    by_premise = _verdict(_recip, "assuming x > 0, for x in [-10,10], f(x) > 0")
    by_domain = _verdict(_recip, "for x in (0,10], f(x) > 0")
    assert by_premise.condition == by_domain.condition


def test_a_premise_relating_two_parameters_carries_its_strictness():
    """A strict premise licenses a strict conclusion and a weak one
    does not; the distinction the assumed-gap machinery has to keep,
    since `a <= b` admits `a == b` where `b - a` is zero.

    The strict half was missing: the ratio check that proves a target
    is a nonnegative multiple of an assumed gap had no strictly
    positive twin, so `assuming a < b` reached only `holds` on
    `b - a > 0`; a claim it should prove outright."""
    strict_premise = _verdict(
        _gap, "assuming a < b, for a in [-10,10], b in [-10,10], f(a,b) > 0")
    assert strict_premise.verdict == "proven", strict_premise.note

    # a multiple of the gap keeps the strictness
    halved = _verdict(
        _half_gap, "assuming a < b, for a in [-10,10], b in [-10,10], f(a,b) > 0")
    assert halved.verdict == "proven", halved.note

    # and the weak premise must NOT prove the strict conclusion: a == b
    # is admitted, and the difference is zero there
    weak_premise = _verdict(
        _gap, "assuming a <= b, for a in [-10,10], b in [-10,10], f(a,b) > 0")
    assert weak_premise.verdict == "falsified", weak_premise.verdict


def test_a_two_parameter_premise_still_falsifies_from_inside_its_region():
    """`b^2 - a^2 >= 0` is false under `a <= b` (a = -8, b = -2), and
    the witness must satisfy the premise."""
    probe = _verdict(
        _sq_gap, "assuming a <= b, for a in [-10,10], b in [-10,10], f(a,b) >= 0")
    assert probe.verdict == "falsified"
    numbers = [float(part) for part in
               probe.counterexample.split(":")[0].strip("() ").split(",")]
    assert numbers[0] <= numbers[1], probe.counterexample


def _half_gap(a, b):
    """Half the difference."""
    return (b - a) / 2.0


def _sq_gap(a, b):
    """Difference of squares."""
    return b * b - a * a
