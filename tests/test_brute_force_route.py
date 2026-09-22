# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A finite declared domain is proved by visiting all of it.

`for n in [30,30] subset Z, f(n) == 0` states one fact about one input.
Checking that input settles the claim completely, so it earns `proven`
rather than the `holds` a sampling loop earns. These tests pin both
halves of that: the verdict is available where the domain really is
finite, and it is refused everywhere the sweep would be standing in for
a region it does not actually cover.
"""
import importlib
import sys
import textwrap

import pytest

import mathema
from mathema.domain import finite_members


def _load(tmp_path, monkeypatch, name, src):
    (tmp_path / f"{name}.py").write_text(textwrap.dedent(src))
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    return importlib.import_module(name)


_DIVISORS = '''
    def divisor_count(n: int) -> int:
        """How many positive divisors n has."""
        total = 0
        for d in range(1, n + 1):
            if n % d == 0:
                total += 1
        return total
'''


@pytest.fixture
def divisor_count(tmp_path, monkeypatch):
    return _load(tmp_path, monkeypatch, "bfmod", _DIVISORS).divisor_count


def _verdict(fn, law):
    (p,) = mathema.claims.check_conjectures(
        fn, [mathema.claim(law, route="derive")])
    return p


# --- finite_members, the enumerability question -----------------------------

def test_finite_members_enumerates_only_genuinely_finite_domains():
    from mathema.conjecture import claim

    def bound(text):
        return claim(text).domain["n"]

    # an integer-typed interval is finite, and open endpoints are honoured
    assert finite_members(bound("for n in [30,30] subset Z, f(n) == 0"),
                          100) == (30,)
    assert finite_members(bound("for n in (1,5) subset Z, f(n) == 0"),
                          100) == (2, 3, 4)
    assert finite_members(bound("for n in [0,3] subset N, f(n) == 0"),
                          100) == (0, 1, 2, 3)
    # a discrete set is finite whatever its type
    assert finite_members(bound("for n in {1,2,3}, f(n) == 0"), 100) == (1, 2, 3)

    # a REAL interval has uncountably many members even with finite ends
    assert finite_members(bound("for n in [1,30], f(n) == 0"), 100) is None
    # an unbounded integer type is infinite: returning () here would let a
    # sweep report a clean pass over no points at all
    assert finite_members(bound("for n in Z, f(n) == 0"), 100) is None
    assert finite_members(bound("for n in N, f(n) == 0"), 100) is None
    # an empty region is not swept: a clean pass over nothing is vacuous
    assert finite_members(bound("for n in (1,2) subset Z, f(n) == 0"),
                          100) is None


def test_finite_members_declines_past_the_budget_instead_of_truncating():
    """The budget bounds the WORK, never the region a verdict covers. A
    truncated sweep reported as a clean pass is sampling with a proof
    label on it."""
    from mathema.conjecture import claim
    bound = claim("for n in [1,500] subset Z, f(n) == 0").domain["n"]
    assert finite_members(bound, 100) is None
    assert len(finite_members(bound, 500)) == 500


# --- the route itself -------------------------------------------------------

def test_a_pinned_domain_proves_by_visiting_its_one_point(divisor_count):
    p = _verdict(divisor_count, "for n in [30,30] subset Z, f(n) == 8")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "derive:brute_force", p.route
    assert "exactly 1 point" in (p.sketch or ""), p.sketch


def test_a_small_finite_domain_proves_across_all_of_it(divisor_count):
    # every n in 2..30 has at least 2 divisors
    p = _verdict(divisor_count, "for n in [2,30] subset Z, f(n) >= 2")
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.route == "derive:brute_force", p.route
    assert "29 points" in (p.sketch or ""), p.sketch


def test_a_false_claim_over_a_finite_domain_is_falsified_with_its_point(
        divisor_count):
    p = _verdict(divisor_count, "for n in [2,30] subset Z, f(n) >= 3")
    assert p.verdict == "falsified", (p.verdict, p.note)
    # the witness came from executing the function at an admitted point,
    # so the route says so rather than being flattened to a probe label
    assert p.route == "derive:brute_force", p.route
    assert "n=2" in (p.counterexample or ""), p.counterexample


def test_a_real_domain_never_takes_this_route(divisor_count):
    """The guard that matters most: a real interval has uncountably many
    points, so no sweep of it is ever complete."""
    p = _verdict(divisor_count, "for n in [2,30], f(n) >= 2")
    assert p.route != "derive:brute_force", (p.route, p.sketch)


def test_an_oversized_finite_domain_declines_rather_than_sampling(
        divisor_count, monkeypatch):
    from mathema import _brute_force
    monkeypatch.setattr(_brute_force, "BRUTE_FORCE_POINT_BUDGET", 5)
    p = _verdict(divisor_count, "for n in [2,30] subset Z, f(n) >= 2")
    assert p.route != "derive:brute_force", (p.route, p.sketch)


def test_an_impure_function_never_takes_this_route(tmp_path, monkeypatch):
    """One evaluation per point is the whole story only for a pure
    function. `is_pure is None` means purity could not be established,
    which is not the same as pure."""
    mod = _load(tmp_path, monkeypatch, "bfimpure", '''
        import random

        def jittered(n: int) -> float:
            """Add noise to n."""
            return n + random.random()
    ''')
    p = _verdict(mod.jittered, "for n in [1,5] subset Z, f(n) >= 1")
    assert p.route != "derive:brute_force", (p.route, p.sketch)


# --- the soundness bar ------------------------------------------------------

def test_a_claim_and_its_negation_are_never_both_proven(divisor_count):
    """The property the whole method exists to protect, asserted for
    this route directly rather than only for the fixtures above."""
    pairs = [("f(n) >= 2", "f(n) < 2"), ("f(n) == 8", "f(n) != 8")]
    for law, negation in pairs:
        a = _verdict(divisor_count, f"for n in [2,30] subset Z, {law}")
        b = _verdict(divisor_count, f"for n in [2,30] subset Z, {negation}")
        assert not (a.verdict == "proven" and b.verdict == "proven"), \
            (law, negation, a.verdict, b.verdict)
