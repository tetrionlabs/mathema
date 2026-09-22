# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""The domain model's symbolic projection agrees with its own numeric
membership test: for every bound shape the grammar can declare,
`bound_to_sympy_set(b).contains(v)` and `domain_contains(v, b)` decide
the same way for real values, endpoints (open and closed), interior
points, outside points, and integer-typing all included. MISSING never
enters the sympy set; its policy is read via `missing_included()`.
"""
import pytest
import sympy

from mathema.domain import (MISSING, Interval, _as_domain, bound_to_sympy_set,
                            domain_contains, is_missing, missing_included,
                            split_quantifier)


BINDINGS = [
    "for x in [0, 1], True",
    "for x in (0, 1), True",
    "for x in (0, 1], True",
    "for x in [0, 1), True",
    "for x in [-5, 5] \\ {0}, True",
    "for x in [-10, -1) | (1, 10], True",
    "for x in {1, 2, 3}, True",
    "for x in [0, 100] \\subset Z, True",
    "for x in Z, True",
    "for x in N, True",
    "for x in [0, 1] \\ {missing}, True",
    "for x in [0,1] | {5} \\subset Z, True",
]

# ints and floats deliberately mixed: `domain_contains` is value-typed
# (an integer-typed domain admits Python ints only, a whole float
# like 0.0 is a representation mismatch, rejected at enforcement time),
# while the sympy projection is mathematical (0 ∈ ℤ regardless of how
# it was spelled). Agreement is therefore asserted per value in its own
# native representation, with float probes skipped on integer-typed
# bounds; there the two semantics differ by design, not by drift.
PROBE_VALUES = [-10, -1, 0, 1, 2, 3, 5, 10, 100, -5,
                -10.0, -1.0, -0.5, 0.0, 0.25, 0.5, 1.0, 1.5, 2.0, 5.0]


@pytest.mark.parametrize("text", BINDINGS)
def test_sympy_set_agrees_with_domain_contains(text):
    domain, _ = split_quantifier(text)
    bound = domain["x"]
    sset = bound_to_sympy_set(bound)
    integer_typed = _as_domain(bound).base_type in ("Z", "N")
    for v in PROBE_VALUES:
        if integer_typed and isinstance(v, float):
            continue
        numeric = domain_contains(v, bound)
        sym_v = sympy.Integer(v) if isinstance(v, int) else sympy.Float(v)
        symbolic = sset.contains(sym_v) == sympy.S.true
        assert numeric == symbolic, (
            f"{text!r}: v={v!r}: domain_contains={numeric}, set says "
            f"{symbolic} (set={sset})")


def test_missing_never_enters_the_sympy_set():
    domain, _ = split_quantifier("for x in [0,100]:float|missing, True")
    bound = domain["x"]
    sset = bound_to_sympy_set(bound)
    assert not any(is_missing(a) for a in getattr(sset, "args", ()))
    assert missing_included(bound)

    strict_domain, _ = split_quantifier("for x in [0, 100] \\ {missing}, True")
    strict = strict_domain["x"]
    assert not missing_included(strict)
    # the numeric set is unchanged by the missing policy
    assert bound_to_sympy_set(strict) == bound_to_sympy_set(Interval(0.0, 100.0))


def test_unstated_bound_projects_to_all_reals_and_admits_missing():
    assert bound_to_sympy_set(None) == sympy.S.Reals
    assert missing_included(None)
    assert domain_contains(MISSING, None)
