# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The built-in stateless claims call a function the way its signature
accepts: a keyword-only parameter by keyword (`f(a, b=b)`), every other
one positionally, so the claim reaches the function rather than
misfitting its signature."""
import random

import mathema
from mathema.conjecture import check_conjectures, claim


def shifted(a, *, b=1):
    return a + b


def noisy_shift(a, *, b=1):
    return a + b + random.random()


def plain(a, b=1):
    return a + b


def _rows(fn, keyword):
    return {p.name: p for p in mathema.check(fn, claims=[keyword]).probes}


def test_stateless_members_call_a_keyword_only_parameter_by_keyword():
    rows = _rows(shifted, "stateless")
    for name in ("is_deterministic", "is_state_safe"):
        p = rows[name]
        assert p.verdict == "proven", (name, p.verdict, p.note)
        assert p.statement == "f(a, b=b) = f(a, b=b)", p.statement


def test_a_nondeterministic_keyword_only_function_is_falsified():
    p = _rows(noisy_shift, "stateless")["is_deterministic"]
    assert p.verdict == "falsified", (p.verdict, p.note)


def test_a_positional_signature_keeps_the_positional_call():
    rows = _rows(plain, "stateless")
    assert rows["is_deterministic"].statement == "f(a, b) = f(a, b)"
    assert rows["is_deterministic"].verdict == "proven"


def test_is_repeatable_children_reach_a_keyword_only_function():
    (p,) = check_conjectures(shifted, [claim("is_repeatable(f)",
                                             route="best")])
    assert p.verdict == "proven", (p.verdict, p.note, p.meta)
    assert p.meta["mathema.children"] == {"is_deterministic": "proven",
                                          "is_state_safe": "proven"}


# --- suggestions that swap or permute arguments ---------------------------

def kw_operands(*, a, b):
    return a + b


def scaled_k(a, *, k=2.0):
    return k * a


def weighted_sum(a, b, *, s=1.0):
    return s * (a + b)


def needs_s(a, b, *, s):
    return s * (a + b)


def weighted_mean(xs, *, w=1.0):
    return w * sum(xs) / len(xs)


def needs_w(xs, *, w):
    return w * sum(xs) / len(xs)


def kw_sequence(*, xs):
    return sum(xs) / len(xs)


def _suggested(fn):
    from mathema.suggest import suggest_claims
    return {c.name: c for c in suggest_claims(fn)}


_SWAPS = ("commutative", "associative", "scale_equivariant",
          "permutation_invariant", "translation_equivariant",
          "self_concat_additive", "order_invariant")


def test_keyword_only_operands_get_no_swap_suggestion():
    names = _suggested(kw_operands)
    assert not set(_SWAPS) & set(names), sorted(names)


def test_a_keyword_only_parameter_is_never_swapped_into_a_slot():
    names = _suggested(scaled_k)
    assert "commutative" not in names and "associative" not in names, \
        sorted(names)


def test_swaps_hold_a_keyword_only_parameter_at_its_default():
    got = _suggested(weighted_sum)
    statements = {n: f"{got[n].lhs} {got[n].relation} {got[n].rhs}"
                  for n in ("commutative", "associative",
                            "scale_equivariant")}
    assert statements["commutative"] == "f(a, b) == f(b, a)"
    assert statements["associative"] == "f(f(a, b), c) == f(a, f(b, c))"
    assert statements["scale_equivariant"] == "f(c*a, c*b) == c*f(a, b)"
    for n in statements:
        assert "s" not in got[n].domain, (n, got[n].domain)
    rows = check_conjectures(weighted_sum, [got[n] for n in statements])
    for p in rows:
        assert p.verdict in ("proven", "holds"), (p.name, p.verdict, p.note)


def test_a_required_keyword_only_parameter_declines_the_swaps():
    names = _suggested(needs_s)
    assert not set(_SWAPS) & set(names), sorted(names)
    names = _suggested(needs_w)
    assert not set(_SWAPS) & set(names), sorted(names)


def test_sequence_transforms_hold_a_keyword_only_parameter_at_its_default():
    got = _suggested(weighted_mean)
    for n in ("permutation_invariant", "scale_equivariant",
              "translation_equivariant"):
        text = f"{got[n].lhs} {got[n].rhs}"
        assert "w" not in text, (n, text)
    p = got["permutation_invariant"]
    assert (p.lhs, p.rhs) == ("f(xs)", "f(g(xs))")
    assert got["bounded_lower"].rhs == "f(xs, w=w)"


def test_a_keyword_only_sequence_gets_no_sequence_transform():
    names = _suggested(kw_sequence)
    assert not set(_SWAPS) & set(names), sorted(names)


def test_derivative_suggestions_pass_a_keyword_only_parameter_by_keyword():
    got = _suggested(scaled_k)
    assert got["monotonic_increasing[a]"].lhs == "d(f(a, k=k), a)"
    assert got["affine[a]"].lhs == "d(f(a, k=k), a, a)"
    got = _suggested(kw_operands)
    assert got["convex[b]"].lhs == "d(f(a=a, b=b), b, b)"


def test_a_keyword_derivative_statement_is_the_family_claim():
    from mathema import families
    from mathema.analysis import effective_facts
    from mathema.conjecture import _statement_is_family_claim
    facts = effective_facts(scaled_k)
    family = families.families()["affine"]
    by_keyword = claim("d(f(a, k=k), a, a) == 0", name="affine[a]")
    assert _statement_is_family_claim(by_keyword, "affine", family, facts)
    (p,) = check_conjectures(scaled_k, [by_keyword])
    assert p.verdict == "proven", (p.verdict, p.note)


def test_numerical_stability_declines_a_keyword_only_parameter():
    assert "is_numerically_stable" not in _suggested(scaled_k)
    assert "is_numerically_stable" not in _suggested(kw_operands)
    assert "is_numerically_stable" in _suggested(plain)
