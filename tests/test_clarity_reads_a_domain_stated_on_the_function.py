# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A domain stated on the function itself, by `@enforce_domain` or by a
guard to a set, is what clarity charges the parameter for.

A parameter `@enforce_domain` holds to three names, or that a guard
refuses outside three names, costs a finite set's bits rather than its
bare type's or a guard boundary's, and an exhaustive proof over that
set clears it, exactly as for a `Literal`. A claim over a set the
enforced domain holds is proven by visiting every member. A bare `str`
parameter a claim binds to three names stays charged for the rest of
its type, and an enforced bounded range costs a bounded range's bits.
"""
import importlib
import math
import sys
import textwrap

import pytest

import mathema
from mathema.badges import (_clarity_profile, _clarity_sources, _reductions,
                            clarity_score)

_SRC = '''
    from mathema import enforce_domain

    @enforce_domain({"name": frozenset({"Alice", " alice ", "ALICE"})})
    def enforced_key(name: str) -> str:
        """The lookup key for a username."""
        return name.strip().lower()

    def guarded_key(name: str) -> str:
        """The lookup key for a username."""
        if name not in {"Alice", " alice ", "ALICE"}:
            raise ValueError(name)
        return name.strip().lower()

    def username_key(name: str) -> str:
        """The lookup key for a username."""
        return name.strip().lower()

    @enforce_domain({"x": (0.0, 1.0)})
    def ranged(x: float) -> float:
        """Twice x."""
        return 2.0 * x
'''

_THREE = '{"Alice", " alice ", "ALICE"}'


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    root = tmp_path_factory.mktemp("stated_domain")
    (root / "stated_domain_mod.py").write_text(textwrap.dedent(_SRC))
    sys.path.insert(0, str(root))
    sys.modules.pop("stated_domain_mod", None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module("stated_domain_mod")
    finally:
        sys.path.remove(str(root))


def _checked(fn, law):
    """The probe a derive-route claim gets, and the row it records."""
    (p,) = mathema.claims.check_conjectures(fn, [mathema.claim(law, route="derive")])
    return p, [{"name": "key", "statement": law, "verdict": p.verdict,
                "route": p.route}]


def _domain_sources(fn):
    """The domain sources of `fn`'s profile, `(bits, reducer)`."""
    return [(bits, reducer) for dim, bits, reducer
            in _clarity_sources(_clarity_profile(fn)) if dim == "domain"]


def _domain_left(fn, rows, param):
    """The bits of `param`'s domain charge the rows leave."""
    profile = _clarity_profile(fn)
    r = _reductions(rows, profile.pure, profile)
    return sum(bits * (1.0 - r.get(reducer, 0.0))
               for _dim, bits, reducer in _clarity_sources(profile)
               if reducer == f"domain_soft:{param}")


# --- @enforce_domain to a finite set ----------------------------------------

def test_an_enforced_set_is_charged_as_a_finite_set(mod):
    (d,) = _clarity_profile(mod.enforced_key).domains
    assert (d.finite, d.points) == (True, 3)
    assert d.bits == pytest.approx(math.log2(3) / 10)
    assert _domain_sources(mod.enforced_key) == [(d.bits, "domain_soft:name")]


def test_a_claim_over_an_enforced_set_is_proven_by_visiting_every_member(mod):
    p, _rows = _checked(mod.enforced_key, 'f(name) == "alice"')
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), (
        p.verdict, p.route, p.note)


def test_a_proof_over_an_enforced_set_clears_the_parameter(mod):
    _p, rows = _checked(mod.enforced_key, 'f(name) == "alice"')
    assert _domain_left(mod.enforced_key, [], "name") > 0
    assert _domain_left(mod.enforced_key, rows, "name") == 0.0
    assert clarity_score(mod.enforced_key, verified_claims=rows) > \
        clarity_score(mod.enforced_key, verified_claims=[])


def test_a_claim_reaching_past_an_enforced_set_is_left_to_the_guard(mod):
    p, _rows = _checked(mod.enforced_key,
                        'for name in {"Alice", "bob"}, f(name) == "alice"')
    assert p.route != "derive:brute_force", (p.verdict, p.route, p.note)
    assert "the executed guard decides" in (p.note or ""), p.note


# --- a guard to a set --------------------------------------------------------

def test_a_guard_to_a_set_is_charged_as_a_finite_set_not_a_boundary(mod):
    (d,) = _clarity_profile(mod.guarded_key).domains
    assert (d.finite, d.points) == (True, 3)
    assert _domain_sources(mod.guarded_key) == [
        (pytest.approx(math.log2(3) / 10), "domain_soft:name")]


def test_a_proof_over_a_guard_s_set_clears_the_parameter(mod):
    p, rows = _checked(mod.guarded_key, 'f(name) == "alice"')
    assert (p.verdict, p.route) == ("proven", "derive:brute_force")
    assert _domain_left(mod.guarded_key, [], "name") > 0
    assert _domain_left(mod.guarded_key, rows, "name") == 0.0


# --- what the function does not state ----------------------------------------

def test_a_bare_str_bound_only_by_the_claim_stays_charged(mod):
    p, rows = _checked(mod.username_key,
                       f'for name in {_THREE}, f(name) == "alice"')
    assert (p.verdict, p.route) == ("proven", "derive:brute_force")
    assert _domain_sources(mod.username_key) == [(1.0, "domain_soft:name")]
    before = _domain_left(mod.username_key, [], "name")
    assert _domain_left(mod.username_key, rows, "name") == \
        pytest.approx(before, abs=1e-9)


# --- @enforce_domain to a bounded range --------------------------------------

def test_an_enforced_bounded_range_is_charged_as_a_bounded_range(mod):
    assert _domain_sources(mod.ranged) == [(0.4, "domain_soft:x")]
