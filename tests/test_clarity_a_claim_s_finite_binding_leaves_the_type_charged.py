# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Whose statement a finite set is decides what a proof over it clears.

When the finite set is the function's own domain (a `Literal`, a str
`Enum`, a guard to a set), a proof that visits every member settles the
parameter, and its domain charge clears. When the finite set comes only
from a claim's binding, the function still accepts every other value of
its type: the proof settles those points only, and the parameter stays
charged for the rest of its type. The brute-force sketch says which of
the two the points came from.
"""
import importlib
import sys
import textwrap

import pytest

import mathema
from mathema.badges import (_clarity_profile, _clarity_sources, _reductions,
                            clarity_score)

_SRC = '''
    from enum import Enum
    from typing import Literal

    def username_key(name: str) -> str:
        """The lookup key for a username."""
        return name.strip().lower()

    def literal_key(name: Literal["Alice", " alice ", "ALICE"]) -> str:
        """The lookup key for a username."""
        return name.strip().lower()

    def guarded_key(name: str) -> str:
        """The lookup key for a username."""
        if name not in {"Alice", " alice ", "ALICE"}:
            raise ValueError(name)
        return name.strip().lower()

    class Side(str, Enum):
        BUY = "buy"
        SELL = "sell"

    def side_word(side: Side) -> str:
        """The side in capitals."""
        return side.value.upper()

    def divisor_count(n: int) -> int:
        """How many positive divisors n has."""
        total = 0
        for d in range(1, n + 1):
            if n % d == 0:
                total += 1
        return total
'''

_THREE = '{"Alice", " alice ", "ALICE"}'


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    root = tmp_path_factory.mktemp("claim_scope")
    (root / "claim_scope_mod.py").write_text(textwrap.dedent(_SRC))
    sys.path.insert(0, str(root))
    sys.modules.pop("claim_scope_mod", None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module("claim_scope_mod")
    finally:
        sys.path.remove(str(root))


def _proven(fn, law):
    """The row a proven brute-force claim records, after checking it."""
    (p,) = mathema.claims.check_conjectures(fn, [mathema.claim(law, route="derive")])
    assert (p.verdict, p.route) == ("proven", "derive:brute_force"), (
        p.verdict, p.route, p.note)
    return p, [{"name": "key", "statement": law, "verdict": p.verdict,
                "route": p.route}]


def _domain_left(fn, rows, param):
    """The bits of `param`'s domain charge the rows leave."""
    profile = _clarity_profile(fn)
    r = _reductions(rows, profile.pure, profile)
    return sum(bits * (1.0 - r.get(reducer, 0.0))
               for _dim, bits, reducer in _clarity_sources(profile)
               if reducer == f"domain_soft:{param}")


# --- a claim's finite binding -----------------------------------------------

def test_a_claim_over_three_names_leaves_a_str_parameter_charged(mod):
    _p, rows = _proven(mod.username_key,
                       f'for name in {_THREE}, f(name) == "alice"')
    before = _domain_left(mod.username_key, [], "name")
    after = _domain_left(mod.username_key, rows, "name")
    assert before > 0.5
    assert after == pytest.approx(before, abs=1e-9), (before, after)


def test_a_claim_over_three_names_of_a_non_identity_kind_leaves_it_charged(mod):
    _p, rows = _proven(mod.username_key,
                       f"for name in {_THREE}, len(f(name)) == 5")
    before = _domain_left(mod.username_key, [], "name")
    assert _domain_left(mod.username_key, rows, "name") == \
        pytest.approx(before, abs=1e-9)


def test_a_claim_over_part_of_a_literal_clears_only_its_share(mod):
    rows = [{"name": "key", "statement": 'for name in {"Alice", "ALICE"}, '
             'f(name) == "alice"', "verdict": "proven",
             "route": "derive:brute_force"}]
    before = _domain_left(mod.literal_key, [], "name")
    after = _domain_left(mod.literal_key, rows, "name")
    assert 0 < after < before
    # two of the three members are settled; the third keeps its share
    (d,) = _clarity_profile(mod.literal_key).domains
    assert after == pytest.approx(d.bits / 3, rel=1e-9)


# --- the function's own finite domain ---------------------------------------

def test_a_proof_over_a_literal_domain_clears_the_parameter(mod):
    _p, rows = _proven(mod.literal_key, 'f(name) == "alice"')
    assert _domain_left(mod.literal_key, [], "name") > 0
    assert _domain_left(mod.literal_key, rows, "name") == 0.0
    assert clarity_score(mod.literal_key, verified_claims=rows) > \
        clarity_score(mod.literal_key, verified_claims=[])


def test_a_claim_binding_the_whole_literal_still_clears_it(mod):
    _p, rows = _proven(mod.literal_key,
                       f'for name in {_THREE}, f(name) == "alice"')
    assert _domain_left(mod.literal_key, rows, "name") == 0.0


def test_a_proof_over_an_enum_domain_clears_the_parameter(mod):
    _p, rows = _proven(mod.side_word, "len(f(side)) >= 3")
    assert _domain_left(mod.side_word, [], "side") > 0
    assert _domain_left(mod.side_word, rows, "side") == 0.0


def test_a_proof_over_a_guard_s_set_clears_the_parameter_s_domain(mod):
    _p, rows = _proven(mod.guarded_key, 'f(name) == "alice"')
    profile = _clarity_profile(mod.guarded_key)
    (d,) = profile.domains
    assert d.finite and d.points == 3
    assert _reductions(rows, profile.pure, profile)["domain_soft:name"] == 1.0


# --- the sketch names where the points came from ----------------------------

def test_the_sketch_of_a_claim_s_binding_says_the_claim_ranges_over_it(mod):
    p, _rows = _proven(mod.username_key,
                       f'for name in {_THREE}, f(name) == "alice"')
    assert "the claim ranges over 3 points, and it holds at every one" in \
        p.sketch, p.sketch
    assert "domain" not in p.sketch, p.sketch


def test_the_sketch_of_a_literal_says_the_function_s_domain(mod):
    p, _rows = _proven(mod.literal_key, 'f(name) == "alice"')
    assert "the function's domain has 3 points, and the claim holds at " \
        "every one" in p.sketch, p.sketch


def test_the_sketch_of_a_guard_says_the_function_s_domain(mod):
    p, _rows = _proven(mod.guarded_key, 'f(name) == "alice"')
    assert "the function's domain has 3 points" in p.sketch, p.sketch


def test_the_sketch_of_an_enum_says_the_function_s_domain(mod):
    p, _rows = _proven(mod.side_word, "len(f(side)) >= 3")
    assert "the function's domain has 2 points" in p.sketch, p.sketch


def test_the_sketch_of_a_one_point_binding_names_the_point(mod):
    p, _rows = _proven(mod.divisor_count, "for n in [30,30] subset Z, f(n) == 8")
    assert "the claim ranges over one point, n = 30, and it holds there" in \
        p.sketch, p.sketch
