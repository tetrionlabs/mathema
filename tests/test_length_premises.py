# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""A length premise bounds the lengths drawn, and a floor still varies.

`assuming dim(xs) >= 20` puts every sampled sequence at length 20 or
more, drawn up to four times the floor (so count-dependent behaviour
past the floor is reached), rather than pinning every trial at exactly
20. A strict bound written with the constant first, `5 > dim(a)`,
admits lengths up to 4, never 5.
"""
from mathema.claims import check_conjectures, claim

_LENGTHS: list = []


def seen(xs: list) -> float:
    _LENGTHS.append(len(xs))
    return float(len(xs))


def _lengths(law):
    _LENGTHS.clear()
    (p,) = check_conjectures(seen, [claim(law, route="probe")])
    assert p.verdict == "holds", (p.verdict, p.note, p.counterexample)
    return list(_LENGTHS)


def test_a_length_floor_draws_more_than_one_length_above_it():
    lengths = _lengths("for xs in R^n, assuming dim(xs) >= 20, f(xs) >= 20")
    assert min(lengths) >= 20, sorted(set(lengths))
    assert len(set(lengths)) > 1, sorted(set(lengths))
    assert max(lengths) <= 80, sorted(set(lengths))


def test_a_strict_bound_with_the_constant_first_excludes_the_constant():
    lengths = _lengths("for xs in R^n, assuming 5 > dim(xs), f(xs) <= 4")
    assert lengths and max(lengths) <= 4, sorted(set(lengths))
    lengths = _lengths("for xs in R^n, assuming 3 < dim(xs), f(xs) >= 4")
    assert lengths and min(lengths) >= 4, sorted(set(lengths))


def test_an_upper_bound_stays_an_upper_bound():
    lengths = _lengths("for xs in R^n, assuming dim(xs) >= 3 and "
                       "dim(xs) <= 5, f(xs) <= 5")
    assert set(lengths) <= {3, 4, 5}, sorted(set(lengths))


class _Resolver:
    def marker_names(self):
        return set()

    def key(self, name, axis):
        return (name, axis)


def _bounds(lhs, relation, rhs):
    from types import SimpleNamespace

    from mathema.conjecture import _shape_constraints
    lo, hi, _groups = _shape_constraints(
        [SimpleNamespace(lhs=lhs, relation=relation, rhs=rhs)], _Resolver())
    key = ("a", 0)
    return lo.get(key), hi.get(key)


def test_the_planned_bounds_of_a_constant_first_comparison():
    assert _bounds("5", ">", "dim(a)")[1] == 4
    assert _bounds("5", ">=", "dim(a)")[1] == 5
    assert _bounds("3", "<", "dim(a)")[0] == 4
    assert _bounds("3", "<=", "dim(a)")[0] == 3
    assert _bounds("dim(a)", "<", "5")[1] == 4
    assert _bounds("dim(a)", ">", "3")[0] == 4
