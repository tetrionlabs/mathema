# SPDX-License-Identifier: BUSL-1.1
# Copyright 2026 Tetrion Ltd
"""Decision A's family tree: a roll-up is falsified when any child it
runs is (the child named in the witness), proven when every child is
proven, and otherwise takes its weakest child's verdict.
is_numerically_defined rolls up is_pole_safe, is_number_set_safe and
is_dimension_safe; is_input_safe rolls up the missing, absent and empty
families; is_computation_safe the overflow, representation and
recursion families; is_finite_over_floats is the view of poles and
overflow."""

import pytest

pytest.importorskip("numpy")

import math  # noqa: E402

import numpy as np  # noqa: E402

from mathema.conjecture import check_conjectures, claim  # noqa: E402
from mathema.types import Mat  # noqa: E402


def reciprocal(x: float) -> float:
    return 1.0 / x


def root(x: float) -> float:
    return math.sqrt(x)


def grow(x: float) -> float:
    return math.exp(x)


def mean_of(xs: list) -> float:
    return sum(xs) / len(xs)


def product(a: Mat("m", "n"), b: Mat("m", "n")):
    return np.asarray(a) @ np.asarray(b)


def _one(fn, text, domain=None):
    (p,) = check_conjectures(fn, [claim(text)], domain=domain)
    return p


def test_a_pole_falsifies_numerical_definedness_naming_the_child():
    p = _one(reciprocal, "is_numerically_defined(f)", {"x": (-1.0, 1.0)})
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("is_pole_safe[x]")


def test_every_child_proven_proves_the_roll_up():
    p = _one(root, "is_numerically_defined(f)", {"x": (1.0, 4.0)})
    assert p.verdict == "proven", (p.verdict, p.note)
    assert p.meta["mathema.children"] == {"is_number_set_safe[x]": "proven"}


def test_an_empty_input_falsifies_input_safety():
    p = _one(mean_of, "is_input_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert p.counterexample.startswith("is_empty_safe[xs]")


def test_overflow_falsifies_computation_safety_and_the_finite_view():
    for name in ("is_computation_safe", "is_finite_over_floats"):
        p = _one(grow, f"{name}(f)", {"x": (0.0, 1000.0)})
        assert p.verdict == "falsified", (name, p.verdict, p.note)
        assert p.counterexample.startswith("is_overflow_safe[x]"), name


def test_operands_that_do_not_fit_falsify_dimension_safety():
    p = _one(product, "is_dimension_safe(f)")
    assert p.verdict == "falsified", (p.verdict, p.note)
    assert "ValueError" in p.counterexample
    p = _one(product, "is_numerically_defined(f)")
    assert p.verdict == "falsified"
    assert p.counterexample.startswith("is_dimension_safe[f]")


def test_bare_definedness_is_falsified_where_a_child_is(monkeypatch):
    # the bare predicate's own executed calls see nothing here, so the
    # verdict is its children's
    import random

    import mathema.claim_families as cf
    from mathema.analysis import analyze_source
    monkeypatch.setattr(cf, "_region_probe",
                        lambda *a, **k: ("holds", 10, None, None))
    verdict, _n, cx, _est, meta = cf._is_defined_probe(
        product, analyze_source(product), claim("is_defined(f)"), {},
        random.Random(0), 20)
    assert verdict == "falsified"
    assert cx.startswith("is_numerically_defined[f]")
    assert meta["mathema.children"]["is_numerically_defined[f]"] \
        == "falsified"
