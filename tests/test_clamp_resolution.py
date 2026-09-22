# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""_proof_support.py's _resolve_clamps(): collapsing a Min/Max clamp
directly against each side's declared domain bound. Covers the
original symbol-vs-literal case (regression guard), the
symbol-vs-symbol case it previously couldn't resolve at all (two
independently domain-bounded parameters, e.g. min(v, v_max)), and the
overlapping-domain case that must stay unresolved rather than guess."""
import sympy

from mathema.symbolic._proof_support import _resolve_clamps

v, v_max, x = sympy.symbols("v v_max x", real=True)


def test_resolves_min_against_a_literal_above_the_range():
    # x in [0, 5]: min(x, 10) is always x
    result = _resolve_clamps(sympy.Min(x, 10), {"x": (0.0, 5.0)}, {"x": x})
    assert result == x


def test_resolves_min_against_a_literal_below_the_range():
    # x in [0, 5]: min(x, -10) is always -10
    result = _resolve_clamps(sympy.Min(x, -10), {"x": (0.0, 5.0)}, {"x": x})
    assert result == -10


def test_leaves_min_unresolved_when_the_literal_is_inside_the_range():
    result = _resolve_clamps(sympy.Min(x, 3), {"x": (0.0, 5.0)}, {"x": x})
    assert result == sympy.Min(x, 3)


def test_resolves_min_between_two_non_overlapping_symbols():
    # v in [10, 20], v_max in [1, 5]: v is always the larger, so
    # min(v, v_max) is always v_max, the real gap this fix closes.
    result = _resolve_clamps(sympy.Min(v, v_max),
                             {"v": (10.0, 20.0), "v_max": (1.0, 5.0)},
                             {"v": v, "v_max": v_max})
    assert result == v_max


def test_resolves_max_between_two_non_overlapping_symbols():
    result = _resolve_clamps(sympy.Max(v, v_max),
                             {"v": (10.0, 20.0), "v_max": (1.0, 5.0)},
                             {"v": v, "v_max": v_max})
    assert result == v


def test_resolves_regardless_of_argument_order():
    result = _resolve_clamps(sympy.Min(v_max, v),
                             {"v": (10.0, 20.0), "v_max": (1.0, 5.0)},
                             {"v": v, "v_max": v_max})
    assert result == v_max


def test_leaves_min_unresolved_when_symbol_domains_overlap():
    # both in [0, 10]: neither side's range is provably always smaller,
    # so this must never collapse; a false collapse here would be a
    # false proof, not just a missed simplification.
    result = _resolve_clamps(sympy.Min(v, v_max),
                             {"v": (0.0, 10.0), "v_max": (0.0, 10.0)},
                             {"v": v, "v_max": v_max})
    assert result == sympy.Min(v, v_max)


def test_leaves_min_unresolved_when_one_side_has_no_declared_domain():
    result = _resolve_clamps(sympy.Min(v, v_max), {"v": (10.0, 20.0)},
                             {"v": v, "v_max": v_max})
    assert result == sympy.Min(v, v_max)


def test_resolves_a_clamp_nested_inside_a_pow():
    # the exact real-world shape this fix was found against:
    # kinetic_energy_capped's 0.5*m*min(v, v_max)**2, confirms the
    # collapse reaches through a surrounding operation, since subs()
    # replaces the node wherever it occurs in the tree.
    expr = sympy.Rational(1, 2) * sympy.Min(v, v_max) ** 2
    result = _resolve_clamps(expr, {"v": (10.0, 20.0), "v_max": (1.0, 5.0)},
                             {"v": v, "v_max": v_max})
    assert result == sympy.Rational(1, 2) * v_max ** 2
