# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""SafetyFamily: the implementation-safety members' shared shape;
the verdict contract both halves run inside, the route a suggestion
declares being read off what the member registers, and the fragility
capability the boundary-jitter check consults."""
import random

import pytest

from mathema.claim_families import SafetyFamily
from mathema.symbolic import ProofResult


def _derive_none(fn, facts, lhs_src, rhs_src, relation, domain=None,
                 tolerance=None):
    return None


def test_suggested_route_reads_the_registered_halves():
    derive_only = SafetyFamily("d_only", derive=_derive_none)
    assert derive_only.suggested_route() == "derive"

    def probe(fn, facts, cj, domain, rng, trials):
        return "holds", 1, None

    with_probe = SafetyFamily("with_probe", derive=_derive_none, probe=probe)
    assert with_probe.suggested_route() == "best"


def test_probe_half_may_never_prove():
    def lying_probe(fn, facts, cj, domain, rng, trials):
        return "proven", 5, None

    member = SafetyFamily("lying", derive=_derive_none, probe=lying_probe)
    run = member.routes()["probe:algorithmic"]
    with pytest.raises(ValueError, match="never prove"):
        run(None, None, None, {}, random.Random(0), 3)


def test_probe_falsification_must_carry_its_witness():
    def witness_less(fn, facts, cj, domain, rng, trials):
        return "falsified", 5, None

    member = SafetyFamily("witless", derive=_derive_none, probe=witness_less)
    run = member.routes()["probe:algorithmic"]
    with pytest.raises(ValueError, match="witness"):
        run(None, None, None, {}, random.Random(0), 3)


def test_derive_disproof_must_carry_its_witness():
    def witness_less(fn, facts, lhs_src, rhs_src, relation, domain=None,
                     tolerance=None):
        return ProofResult("disproven", sketch="broken by construction")

    member = SafetyFamily("witless_derive", derive=witness_less)
    run = member.routes()["derive"]
    with pytest.raises(ValueError, match="witness"):
        run(None, None, "x", "", "is_pole_safe")


def test_compliant_halves_pass_through_unchanged():
    def derive(fn, facts, lhs_src, rhs_src, relation, domain=None,
               tolerance=None):
        return ProofResult("disproven", sketch="pole inside",
                           counterexample="x = 0")

    def probe(fn, facts, cj, domain, rng, trials):
        return "falsified", 2, "x = 0 raised"

    member = SafetyFamily("compliant", derive=derive, probe=probe)
    proof = member.routes()["derive"](None, None, "x", "", "is_pole_safe")
    assert proof.status == "disproven" and proof.counterexample == "x = 0"
    verdict, checked, cx, established = member.routes()["probe:algorithmic"](
        None, None, None, {}, random.Random(0), 3)
    assert (verdict, checked, cx) == ("falsified", 2, "x = 0 raised")
    assert established is None


def test_trials_may_prove_only_with_an_established_sketch():
    def exhaustive(fn, facts, cj, domain, rng, trials):
        return ("proven", 2, None,
                "the hazard class has exactly two cases; both observed")

    member = SafetyFamily("exhaustive", derive=_derive_none,
                          probe=exhaustive)
    verdict, checked, cx, established = member.routes()["probe:algorithmic"](
        None, None, None, {}, random.Random(0), 3)
    assert verdict == "proven" and "both observed" in established

    def overreaching(fn, facts, cj, domain, rng, trials):
        return "proven", 40, None

    bad = SafetyFamily("overreach", derive=_derive_none, probe=overreaching)
    with pytest.raises(ValueError, match="exhaustive"):
        bad.routes()["probe:algorithmic"](None, None, None, {},
                                          random.Random(0), 3)
